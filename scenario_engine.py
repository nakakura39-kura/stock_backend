import numpy as np
from sklearn.cluster import KMeans

def classify_scenario_shape(path: np.ndarray) -> str:
    """
    경로의 형태(Shape)를 물리적으로 분석하여 적절한 시나리오 이름을 부여합니다.
    path: [day0, day1, day2, day3, day4, day5] (기준일 대비 비율 또는 수익률)
    """
    total_return = (path[-1] - path[0]) / path[0] if path[0] != 0 else 0
    max_val = np.max(path)
    min_val = np.min(path)
    max_idx = np.argmax(path)
    min_idx = np.argmin(path)
    
    # 1. 강력한 상승
    if total_return >= 0.03 and max_idx >= 3:
        return "상승 지속"
    
    # 2. 상승 후 조정 (중간에 고점을 찍고 밀린 경우)
    elif max_idx in [1, 2, 3] and (max_val - path[0]) / path[0] >= 0.02 and total_return < (max_val - path[0]) / path[0] * 0.5:
        return "상승 후 조정"
        
    # 3. 하락 후 반등 (초기 하락 후 회복)
    elif min_idx in [1, 2] and (path[0] - min_val) / path[0] >= 0.02 and total_return > -0.01:
        return "하락 후 반등"
        
    # 4. 명확한 하락
    elif total_return <= -0.02:
        return "하락 전환"
        
    # 5. 횡보 / 박스권
    else:
        return "박스권 횡보"

def generate_scenarios_from_past_patterns(similar_past_returns: np.ndarray):
    """
    similar_past_returns: Shape (N, 6) -> 유사 패턴들의 과거 5일 미래 경로
    """
    n_samples = len(similar_past_returns)
    
    # 표본 수 경고 플래그 (30개 미만 시 신뢰도 낮음)
    is_low_sample = n_samples < 30
    
    if n_samples < 3:
        return {
            "error": "표본 수가 부족하여 통계적 시나리오를 생성할 수 없습니다.",
            "sample_count": n_samples
        }

    # 1. K-Means 클러스터링 (3개 군집)
    n_clusters = min(3, n_samples)
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(similar_past_returns)
    centroids = kmeans.cluster_centers_

    # 2. 각 클러스터별 빈도수 (통계적 패턴 분포 %)
    counts = np.bincount(labels, minlength=n_clusters)
    probabilities = (counts / n_samples) * 100

    scenarios = []
    
    for i in range(n_clusters):
        centroid_path = centroids[i]
        # 경로 형태 분석을 통해 시나리오 이름 동적 결정 (확률순 X)
        scenario_name = classify_scenario_shape(centroid_path)
        
        scenarios.append({
            "name": scenario_name,
            "distribution_ratio": round(probabilities[i], 1), # 해당 패턴 유형의 과거 분포 비율
            "path": centroid_path.tolist(),
            "sample_count": int(counts[i])
        })

    # 3. 확률(분포비율) 높은 순으로 정렬 (이름은 고정된 채 비율순 배치만 변경)
    scenarios = sorted(scenarios, key=lambda x: x["distribution_ratio"], reverse=True)

    # 4. 복합 예측 신뢰도(Composite Confidence) 계산
    # A) Sample Size Score (표본 수 점수: 100개 기준)
    sample_score = min(1.0, n_samples / 100.0) * 30  # 만점 30점

    # B) Direction Agreement Score (상승/하락 방향 일치율)
    final_returns = similar_past_returns[:, -1] - similar_past_returns[:, 0]
    up_ratio = np.sum(final_returns > 0) / n_samples
    direction_score = max(up_ratio, 1 - up_ratio) * 40  # 만점 40점

    # C) Cluster Separation Score (경로 응집도/분리도)
    inertia = kmeans.inertia_
    separation_score = max(0, 30 - (inertia / n_samples) * 100) # 만점 30점

    total_confidence = round(sample_score + direction_score + separation_score, 1)
    total_confidence = max(10.0, min(99.0, total_confidence))

    return {
        "confidence": total_confidence,
        "sample_count": n_samples,
        "is_low_sample": is_low_sample,
        "scenarios": scenarios
    }