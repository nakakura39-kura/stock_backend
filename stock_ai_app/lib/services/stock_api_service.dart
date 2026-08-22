// lib/services/stock_api_service.dart

import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/scenario_model.dart';

class StockApiService {
  // 플랫폼에 맞춘 Base URL 지정
  static String get baseUrl {
    if (Platform.isAndroid) {
      return "http://10.0.2.2:8000"; // 안드로이드 에뮬레이터용
    } else {
      return "http://127.0.0.1:8000"; // iOS 시뮬레이터 및 Windows 데스크톱용
    }
  }

  /// 시나리오 예측 API 호출 함수
  static Future<ScenarioResponse> fetchStockScenario(String symbol) async {
    final url = Uri.parse('$baseUrl/api/v1/stock/scenario');

    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'symbol': symbol}),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final Map<String, dynamic> decodedData = jsonDecode(utf8.decode(response.bodyBytes));
        return ScenarioResponse.fromJson(decodedData);
      } else {
        throw Exception("서버 에러 (${response.statusCode}): ${response.body}");
      }
    } catch (e) {
      throw Exception("시나리오 API 호출 실패: $e");
    }
  }
}