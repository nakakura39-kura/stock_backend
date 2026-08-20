# C:\samsungAI\scorer.py

from config import WEIGHTS

def calculate_total_score(scores: dict) -> dict:
    """타임프레임별 가중치 종합 점수 계산"""
    total_score = 0.0
    total_weight = 0.0
    
    for key, weight in WEIGHTS.items():
        if key in scores and scores[key] is not None:
            total_score += scores[key] * weight
            total_weight += weight
            
    final_score = (total_score / total_weight) if total_weight > 0 else 0.0
    return {
        "final_score": round(final_score, 1),
        "breakdown": scores
    }