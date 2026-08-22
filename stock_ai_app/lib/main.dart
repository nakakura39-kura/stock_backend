import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:fl_chart/fl_chart.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Stock AI Assistant',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF121212),
        primaryColor: Colors.blueAccent,
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF1E1E1E),
          elevation: 0,
        ),
      ),
      home: const MainDashboard(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class MainDashboard extends StatefulWidget {
  const MainDashboard({super.key});

  @override
  State<MainDashboard> createState() => _MainDashboardState();
}

class _MainDashboardState extends State<MainDashboard> {
  int _selectedIndex = 0;

  final _symbolController = TextEditingController(text: '삼성전자');
  final _cashController = TextEditingController(text: '5000000');
  final _qtyController = TextEditingController(text: '50');
  final _priceController = TextEditingController(text: '75000');

  bool _isLoading = false;
  Map<String, dynamic>? _apiData;
  List<dynamic> _chartList = [];

  final String _baseUrl = "https://stock-backend-api-yacs.onrender.com/api/v1/stock";

  Future<void> _fetchAnalysis() async {
    setState(() => _isLoading = true);
    final symbol = _symbolController.text.trim();

    try {
      final analyzeUri = Uri.parse("$_baseUrl/analyze?symbol=${Uri.encodeComponent(symbol)}");
      final response = await http.get(analyzeUri).timeout(const Duration(seconds: 45));

      final chartUri = Uri.parse("$_baseUrl/candles?symbol=${Uri.encodeComponent(symbol)}&days=365");
      final chartResponse = await http.get(chartUri).timeout(const Duration(seconds: 45));

      if (response.statusCode == 200) {
        setState(() {
          _apiData = jsonDecode(utf8.decode(response.bodyBytes));
          if (chartResponse.statusCode == 200) {
            _chartList = jsonDecode(utf8.decode(chartResponse.bodyBytes));
          }
        });
      } else {
        final err = jsonDecode(utf8.decode(response.bodyBytes));
        _showErrorSnackBar("서버 에러: ${err['detail'] ?? response.statusCode}");
      }
    } catch (e) {
      _showErrorSnackBar("통신 에러 (Render 서버 대기 중일 수 있습니다): $e");
    } finally {
      setState(() => _isLoading = false);
    }
  }

  void _showErrorSnackBar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.redAccent),
    );
  }

  @override
  void initState() {
    super.initState();
    _fetchAnalysis();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("🤖 Stock samsungAI"),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchAnalysis,
          )
        ],
      ),
      body: _isLoading
          ? const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(color: Colors.blueAccent),
                  SizedBox(height: 16),
                  Text(
                    "samsungAI 엔진 분석 중...\n(첫 접속 시 최대 30초 소요될 수 있습니다)",
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                ],
              ),
            )
          : _apiData == null
              ? Center(
                  child: ElevatedButton(
                    onPressed: _fetchAnalysis,
                    child: const Text("다시 시도"),
                  ),
                )
              : IndexedStack(
                  index: _selectedIndex,
                  children: [
                    _buildAnalysisTab(),
                    _buildPredictionTab(),
                  ],
                ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedIndex,
        onTap: (index) => setState(() => _selectedIndex = index),
        selectedItemColor: Colors.blueAccent,
        unselectedItemColor: Colors.grey,
        backgroundColor: const Color(0xFF1E1E1E),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.analytics), label: '분석'),
          BottomNavigationBarItem(icon: Icon(Icons.show_chart), label: '차트/예측'),
        ],
      ),
    );
  }

  Widget _buildAnalysisTab() {
    final currentPrice = _chartList.isNotEmpty ? _chartList.last['close'] ?? 0 : 0;
    final qty = int.tryParse(_qtyController.text) ?? 0;
    final avgPrice = double.tryParse(_priceController.text) ?? 0;
    
    final totalEval = qty * currentPrice;
    final totalCost = qty * avgPrice;
    final pnl = totalEval - totalCost;
    final pnlPct = totalCost > 0 ? (pnl / totalCost * 100) : 0.0;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _symbolController,
                  decoration: const InputDecoration(
                    labelText: '종목명 또는 코드 (예: 삼성전자, 005930)',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              ElevatedButton(
                onPressed: _fetchAnalysis,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blueAccent,
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
                ),
                child: const Text("조회", style: TextStyle(color: Colors.white)),
              )
            ],
          ),
          const SizedBox(height: 16),

          Card(
            color: const Color(0xFF2A2A2A),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(14.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text("💼 내 자산 정보", style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.blueAccent)),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _cashController,
                          decoration: const InputDecoration(labelText: '예수금 (원)', border: OutlineInputBorder()),
                          keyboardType: TextInputType.number,
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: _qtyController,
                          decoration: const InputDecoration(labelText: '보유 수량 (주)', border: OutlineInputBorder()),
                          keyboardType: TextInputType.number,
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _priceController,
                    decoration: const InputDecoration(labelText: '평균 단가 (원)', border: OutlineInputBorder()),
                    keyboardType: TextInputType.number,
                    onChanged: (_) => setState(() {}),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          Card(
            color: const Color(0xFF1E293B),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: ListTile(
              title: Text("현재가: $currentPrice 원", style: const TextStyle(fontWeight: FontWeight.bold)),
              subtitle: Text(
                "평가손익: ${pnl.toInt()} 원 (${pnlPct.toStringAsFixed(2)}%)",
                style: TextStyle(
                  color: pnl >= 0 ? Colors.redAccent : Colors.blueAccent,
                ),
              ),
              trailing: Chip(
                label: Text(
                  _apiData!['overall_status'] ?? _apiData!['status'] ?? "분석완료",
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                ),
                backgroundColor: Colors.blueAccent,
              ),
            ),
          ),
          const SizedBox(height: 20),

          const Text("📊 samsungAI 진단 스코어", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.cyanAccent)),
          const SizedBox(height: 8),
          Card(
            color: const Color(0xFF1E1E1E),
            child: Padding(
              padding: const EdgeInsets.all(12.0),
              child: Text(
                jsonEncode(_apiData),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPredictionTab() {
    List<FlSpot> spots = [];

    for (int i = 0; i < _chartList.length; i++) {
      final close = (_chartList[i]['close'] as num?)?.toDouble() ?? 0.0;
      spots.add(FlSpot(i.toDouble(), close));
    }

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text("최근 주가 추이 (1년 캔들)", style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.grey)),
          const SizedBox(height: 12),
          Expanded(
            child: spots.isEmpty
                ? const Center(child: Text("차트 데이터가 없습니다."))
                : Container(
                    padding: const EdgeInsets.only(right: 16, top: 10, bottom: 10),
                    child: LineChart(
                      LineChartData(
                        gridData: const FlGridData(show: true, drawVerticalLine: false),
                        titlesData: const FlTitlesData(
                          topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                          rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                        ),
                        borderData: FlBorderData(show: true, border: Border.all(color: Colors.white24)),
                        lineBarsData: [
                          LineChartBarData(
                            spots: spots,
                            isCurved: false,
                            color: Colors.cyanAccent,
                            barWidth: 1.5,
                            dotData: const FlDotData(show: false),
                          ),
                        ],
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}