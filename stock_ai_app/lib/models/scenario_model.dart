// lib/models/scenario_model.dart

class ScenarioItem {
  final int rank;
  final String name;
  final double probability;
  final String finalReturn;
  final List<double> path;

  ScenarioItem({
    required this.rank,
    required this.name,
    required this.probability,
    required this.finalReturn,
    required this.path,
  });

  factory ScenarioItem.fromJson(Map<String, dynamic> json) {
    return ScenarioItem(
      rank: json['rank'] ?? 0,
      name: json['name'] ?? '',
      probability: (json['probability'] as num).toDouble(),
      finalReturn: json['final_return'] ?? '0.0%',
      path: (json['path'] as List<dynamic>)
          .map((e) => (e as num).toDouble())
          .toList(),
    );
  }
}

class ScenarioResponse {
  final String symbol;
  final int matchedCount;
  final double predictionConfidence;
  final List<ScenarioItem> scenarios;

  ScenarioResponse({
    required this.symbol,
    required this.matchedCount,
    required this.predictionConfidence,
    required this.scenarios,
  });

  factory ScenarioResponse.fromJson(Map<String, dynamic> json) {
    final data = json['data'] ?? {};
    return ScenarioResponse(
      symbol: json['symbol'] ?? '',
      matchedCount: data['matched_count'] ?? 0,
      predictionConfidence: (data['prediction_confidence'] as num).toDouble(),
      scenarios: (data['scenarios'] as List<dynamic>?)
              ?.map((item) => ScenarioItem.fromJson(item))
              .toList() ??
          [],
    );
  }
}