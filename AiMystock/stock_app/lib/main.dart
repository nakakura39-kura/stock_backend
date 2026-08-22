import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:fl_chart/fl_chart.dart';

void main() {
  runApp(const StockAiApp());
}

class StockAiApp extends StatelessWidget {
  const StockAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Stock Trader',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF121212),
        primaryColor: const Color(0xFF00E676),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00E676),
          surface: Color(0xFF1E1E1E),
        ),
      ),
      home: const StockHomeScreen(),
    );
  }
}

class StockHomeScreen extends StatefulWidget {
  const StockHomeScreen({super.key});

  @override
  State<StockHomeScreen> createState() => _StockHomeScreenState();
}

class _StockHomeScreenState extends State<StockHomeScreen> {
  final TextEditingController _symbolController = TextEditingController(text: 'AAPL');
  
  // Render.com 클라우드 백엔드 URL
  final String _baseUrl = 'https://stock-backend-api-yacs.onrender.com';
  
  bool _isLoading = false;
  String _errorMessage = '';
  
  String _currentSymbol = 'AAPL';
  List<dynamic> _candles = [];
  Map<String, dynamic>? _aiSignal;

  @override
  void initState() {
    super.initState();
    _fetchStockData('AAPL');
  }

  Future<void> _fetchStockData(String symbol) async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      // 1. 캔들 차트 데이터 수집
      final response = await http.get(
        Uri.parse('$_baseUrl/api/v1/stock/candles?symbol=$symbol&timeframe=D&days=100'),
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        
        setState(() {
          _currentSymbol = symbol.toUpperCase();
          _candles = data;
          
          // 기술적 지표 타점 시뮬레이션
          if (data.isNotEmpty) {
            final double lastClose = double.parse(data.last['close'].toString());
            final double prevClose = data.length > 1 ? double.parse(data[data.length - 2]['close'].toString()) : lastClose;
            final double change = ((lastClose - prevClose) / prevClose) * 100;

            _aiSignal = {
              'status': change >= 0 ? 'BUY' : 'WAIT',
              'score': (75 + (change * 2)).clamp(0, 99).toInt(),
              'targetPrice': (lastClose * 1.05).toStringAsFixed(2),
              'stopLoss': (lastClose * 0.95).toStringAsFixed(2),
              'lastClose': lastClose.toStringAsFixed(2),
              'change': change.toStringAsFixed(2),
            };
          }
        });
      } else {
        setState(() {
          _errorMessage = '종목을 찾을 수 없거나 서버 응답 오류가 발생했습니다.';
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = '서버 통신 실패 (Render.com 첫 접속 시 약 30초 소요될 수 있습니다)';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('⚡ AI Stock Trader', style: TextStyle(fontWeight: FontWeight.bold)),
        elevation: 0,
        backgroundColor: const Color(0xFF1E1E1E),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            // 🔍 종목 검색 입력창
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _symbolController,
                    decoration: InputDecoration(
                      hintText: '종목코드 입력 (예: AAPL, 005930)',
                      filled: true,
                      fillColor: const Color(0xFF2C2C2C),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                      prefixIcon: const Icon(Icons.search, color: Colors.grey),
                    ),
                    onSubmitted: (val) => _fetchStockData(val.trim()),
                  ),
                ),
                const SizedBox(width: 10),
                ElevatedButton(
                  onPressed: () => _fetchStockData(_symbolController.text.trim()),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF00E676),
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text('검색', style: TextStyle(fontWeight: FontWeight.bold)),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // 🔄 로딩 & 에러 처리
            if (_isLoading)
              const Expanded(
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(color: Color(0xFF00E676)),
                      SizedBox(height: 16),
                      Text('Render.com 클라우드에서 AI 주가 분석 중...', style: TextStyle(color: Colors.grey)),
                    ],
                  ),
                ),
              )
            else if (_errorMessage.isNotEmpty)
              Expanded(
                child: Center(
                  child: Text(_errorMessage, style: const TextStyle(color: Colors.redAccent)),
                ),
              )
            else ...[
              // 📊 AI 매수/매도 타점 리포트 카드
              if (_aiSignal != null) ...[
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E1E),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: _aiSignal!['status'] == 'BUY' ? const Color(0xFF00E676) : Colors.orangeAccent,
                      width: 1.5,
                    ),
                  ),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('[$_currentSymbol] AI 분석 결과', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: _aiSignal!['status'] == 'BUY' ? Colors.green.withOpacity(0.2) : Colors.orange.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              _aiSignal!['status'] == 'BUY' ? '🚀 매수 추천' : '⏸️ 관망/대기',
                              style: TextStyle(
                                color: _aiSignal!['status'] == 'BUY' ? const Color(0xFF00E676) : Colors.orangeAccent,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          )
                        ],
                      ),
                      const Divider(color: Colors.white24, height: 24),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceAround,
                        children: [
                          _buildStatItem('현재가', '\$${_aiSignal!['lastClose']}'),
                          _buildStatItem('AI 신뢰도', '${_aiSignal!['score']}점'),
                          _buildStatItem('목표가', '\$${_aiSignal!['targetPrice']}'),
                          _buildStatItem('손절가', '\$${_aiSignal!['stopLoss']}'),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // 📈 주가 종가 라인 차트
              Expanded(
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E1E),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('최근 100일 주가 추이', style: TextStyle(color: Colors.grey, fontSize: 12)),
                      const SizedBox(height: 10),
                      Expanded(
                        child: LineChart(
                          LineChartData(
                            gridData: const FlGridData(show: false),
                            titlesData: const FlTitlesData(show: false),
                            borderData: FlBorderData(show: false),
                            lineBarsData: [
                              LineChartBarData(
                                spots: _candles.asMap().entries.map((e) {
                                  return FlSpot(
                                    e.key.toDouble(),
                                    double.parse(e.value['close'].toString()),
                                  );
                                }).toList(),
                                isCurved: true,
                                color: const Color(0xFF00E676),
                                barWidth: 2,
                                isStrokeCapRound: true,
                                dotData: const FlDotData(show: false),
                                belowBarData: BarAreaData(
                                  show: true,
                                  color: const Color(0xFF00E676).withOpacity(0.15),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildStatItem(String label, String value) {
    return Column(
      children: [
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
      ],
    );
  }
}