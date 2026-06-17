


from sklearn.cluster import KMeans
from sklearn import metrics
import matplotlib.pyplot as plt

def plot_cluster(df, feature_li, max_loop=50):
    """
    绘制不同数量簇下聚类的表现情况
    :param df: 加工好的输入数据
    :param feature_li: 数据中的特征列
    :param max_loop: 最大尝试的簇数量
    """
    X = df[feature_li]
    sse_within_cluster = {}
    silhouette_score = {}
    
    for k in range(2, max_loop):
        kmeans = KMeans(n_clusters=k, random_state=10, n_init=10)
        kmeans.fit(X)
        sse_within_cluster[k] = kmeans.inertia_
        silhouette_score[k] = metrics.silhouette_score(X, kmeans.labels_, random_state=10)
    
    plt.figure(figsize=(10, 6))
    plt.subplot(211)
    plt.plot(list(sse_within_cluster.keys()), list(sse_within_cluster.values()))
    plt.xlabel("簇的数量")
    plt.ylabel("簇内误差平方和")
    plt.title("K-Means聚类后的簇内误差平方和")
    plt.xticks([i for i in range(2, max_loop)])
    
    plt.subplot(212)
    plt.plot(list(silhouette_score.keys()), list(silhouette_score.values()))
    plt.xlabel("簇的数量")
    plt.ylabel("轮廓系数值")
    plt.title("K-Means聚类后的轮廓系数值")
    plt.xticks([i for i in range(2, max_loop)])
    
    plt.subplots_adjust(top=0.92, bottom=0.08, left=0.10, right=0.95, hspace=0.5, wspace=0.35)








def apply_cluster(df, feature_li, clusters=2):
    """
    应用聚类
    :param df: 处理好的输入数据
    :param feature_li: 特征列
    :param clusters: 设置的聚类数量
    :return: 最终的聚类结果
    """
    X = df[feature_li]
    kmeans = KMeans(n_clusters=clusters, random_state=10, n_init=10)
    kmeans.fit(X)
    score = metrics.silhouette_score(X, kmeans.labels_, random_state=10)
    df['cluster'] = kmeans.labels_
    sse_within_cluster = kmeans.inertia_
    
    print("clustering performance")
    print("--------------------")
    print(f"silhouette score: {score:.2f}")
    print(f"sse within cluster: {sse_within_cluster:.2f}")
    
    return df

# 计算聚类后各簇的平均年收益和平均方差值
first_cluster = apply_cluster(df_clean, clusters=5)
first_cluster_out = (
    first_cluster
    .groupby('cluster')
    .agg({
        "数量": "count",
        "平均年收益": "mean",
        "平均方差值": "mean"
    })
    .sort_values('平均年收益')
    .reset_index()
)


