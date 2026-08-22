// lib/widgets/scenario_chart_widget.dart

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../models/scenario_model.dart';

class ScenarioChartWidget extends StatelessWidget {
  final List<ScenarioItem> scenarios;
  final double currentPrice; // 현재 주가 (원 또는 $)
  final String symbol;       // 종목코드/티커

  const ScenarioChartWidget({
    Key? key,
    required this.scenarios,
    required this.currentPrice,
    required this.symbol,
  }) : super(key: key);

  Color _getScenarioColor(int rank) {
    switch (rank) {
      case 1:
        return const Color(0xFF26A69A); // Teal
      case 2:
        return const Color(0xFF29B6F6); // Blue
      case 3:
        return const Color(0xFFEF5350); // Red
      default:
        return Colors.grey;
    }
  }

  // 미국주식($)과 한국주식(원) 단위 구분 표시
  String _formatPrice(double price) {
    final bool isUsStock = RegExp(r'^[A-Za-z]+$').hasMatch(symbol);
    if (isUsStock) {
      return "\$${price.toStringAsFixed(1)}";
    } else {
      // 한국 주식 천단위 콤마
      final formatter = NumberFormat('#,###');
      return "${formatter.format(price.round())}원";
    }
  }

  // 오늘 날짜 기준으로 영업일 날짜 계산 (주말 제외)
  List<DateTime> _calculateFutureDates(int count) {
    List<DateTime> dates = [];
    DateTime current = DateTime.now();
    dates.add(current); // D+0 (오늘)

    while (dates.length < count) {
      current = current.add(const Duration(days: 1));
      // 토요일(6), 일요일(7) 제외한 영업일 기준
      if (current.weekday != DateTime.saturday && current.weekday != DateTime.sunday) {
        dates.add(current);
      }
    }
    return dates;
  }

  @override
  Widget build(BuildContext context) {
    if (scenarios.isEmpty) {
      return const SizedBox(
        height: 240,
        child: Center(child: Text("차트 데이터가 없습니다.")),
      );
    }

    final futureDates = _calculateFutureDates(6); // D+0 ~ D+5 (총 6일)

    return Container(
      height: 280,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2C),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 범례 (Legend)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: scenarios.map((s) {
              final color = _getScenarioColor(s.rank);
              return Row(
                children: [
                  Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                  const SizedBox(width: 4),
                  Text(
                    "${s.name.split(' ')[0]} (${s.probability}%)",
                    style: const TextStyle(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.bold),
                  ),
                ],
              );
            }).toList(),
          ),
          const SizedBox(height: 16),

          // 라인 차트 영역
          Expanded(
            child: LineChart(
              LineChartData(
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (value) {
                    return FlLine(
                      color: value == currentPrice ? Colors.white38 : Colors.white10,
                      strokeWidth: value == currentPrice ? 1.5 : 0.8,
                    );
                  },
                ),
                titlesData: FlTitlesData(
                  // X축: 실제 날짜 (예: 8/24)
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 22,
                      interval: 1,
                      getTitlesWidget: (value, meta) {
                        final int index = value.toInt();
                        if (index >= 0 && index < futureDates.length) {
                          final date = futureDates[index];
                          return Text(
                            "${date.month}/${date.day}",
                            style: const TextStyle(color: Colors.white54, fontSize: 10),
                          );
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  ),
                  // Y축: 금액 기준 (원 / $)
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 55,
                      getTitlesWidget: (value, meta) {
                        return Text(
                          _formatPrice(value),
                          style: const TextStyle(color: Colors.white54, fontSize: 9),
                        );
                      },
                    ),
                  ),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                ),
                borderData: FlBorderData(show: false),

                // 터치 시 금액 기준 툴팁 출력
                lineTouchData: LineTouchData(
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipColor: (spot) => Colors.black87,
                    getTooltipItems: (touchedSpots) {
                      return touchedSpots.map((spot) {
                        final scenario = scenarios[spot.barIndex];
                        return LineTooltipItem(
                          "${scenario.name}\n예상가: ${_formatPrice(spot.y)}",
                          TextStyle(
                            color: _getScenarioColor(scenario.rank),
                            fontWeight: FontWeight.bold,
                            fontSize: 11,
                          ),
                        );
                      }).toList();
                    },
                  ),
                ),

                // 수익률(%) 데이터를 실제 주가 금액으로 변환하여 차트에 플롯
                lineBarsData: scenarios.map((scenario) {
                  final color = _getScenarioColor(scenario.rank);

                  final spots = List<FlSpot>.generate(
                    scenario.path.length,
                    (index) {
                      final returnRate = scenario.path[index]; // 예: +1.43%
                      final calculatedPrice = currentPrice * (1 + (returnRate / 100)); // 현재가 기준 금액 산출
                      return FlSpot(index.toDouble(), calculatedPrice);
                    },
                  );

                  return LineChartBarData(
                    spots: spots,
                    isCurved: true,
                    color: color,
                    barWidth: scenario.rank == 1 ? 3.0 : 1.8,
                    isStrokeCapRound: true,
                    dotData: FlDotData(
                      show: true,
                      getDotPainter: (spot, percent, barData, index) {
                        return FlDotCirclePainter(
                          radius: 2.5,
                          color: color,
                          strokeWidth: 1,
                          strokeColor: Colors.white,
                        );
                      },
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}