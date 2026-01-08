import pandas as pd
import jieba  # 需要安装: pip install jieba
import numpy as np

# 1. 定义情感词典 (这是最基础的NLP，展示给老师看你的思路)
POSITIVE_WORDS = [
    "涨", "上扬", "突破", "利好", "新高", "合作", "发布", "元年", 
    "增长", "超预期", "买入", "增持", "旺季", "落地", "受益"
]

NEGATIVE_WORDS = [
    "跌", "下挫", "跳水", "利空", "新低", "立案", "调查", "亏损", 
    "不及预期", "卖出", "减持", "风险", "制裁", "限制"
]

def calculate_sentiment(text):
    """
    简单的情感打分函数
    逻辑：(积极词数量 - 消极词数量)
    """
    if pd.isna(text):
        return 0
    
    score = 0
    # 简单分词（其实只要包含子字符串就行，为了演示流程用 jieba）
    # 这里偷懒直接用字符串匹配，效率更高
    for w in POSITIVE_WORDS:
        if w in text:
            score += 1
    for w in NEGATIVE_WORDS:
        if w in text:
            score -= 1
    return score

def main():
    # 1. 读取刚才抓取的数据
    input_file = "Mapping_Factor_Raw_Data.csv"
    print(f"正在读取 {input_file} ...")
    try:
        df = pd.read_csv(input_file)
    except FileNotFoundError:
        print("没找到文件，请先运行上一步的抓取代码！")
        return

    # 2. 计算情感因子 (Sentiment Factor)
    print("正在计算新闻情感因子...")
    df['sentiment_score'] = df['title'].apply(calculate_sentiment)

    # 3. 构建“联动强度” (Linkage Strength)
    # 逻辑：如果新闻里明确提到了具体的 美股代码/公司名，权重更高
    # 这里我们复用 'matched_keywords' 列，如果有匹配，基础分为 1
    df['linkage_strength'] = df['matched_keywords'].apply(lambda x: 1 if pd.notna(x) else 0)

    # 4. 合成最终因子 (Final Factor)
    # 简单公式：最终因子 = 联动强度 * 情感分数
    df['factor_value'] = df['linkage_strength'] * df['sentiment_score']

    # 5. 生成交易信号 (Signal)
    # 规则：因子值 >= 1 看多，<= -1 看空，0 观望
    def get_signal(val):
        if val >= 1:
            return "做多 (Long)"
        elif val <= -1:
            return "做空 (Short)"
        else:
            return "中性 (Neutral)"

    df['signal'] = df['factor_value'].apply(get_signal)

    # --- 展示结果 ---
    print("\n" + "="*50)
    print("因子计算完成！预览如下：")
    print("="*50)
    
    # 选取关键列展示
    cols = ['public_time', 'stock_name', 'title', 'sentiment_score', 'signal']
    print(df[cols])

    # 保存结果给老师看
    output_file = "Mapping_Factor_Result.csv"
    df.to_csv(output_file, index=False, encoding="utf_8_sig")
    print(f"\n结果已保存至: {output_file}")
    print("这是你要发给老师看的最终表格，证明你完成了从【数据】到【因子】的闭环。")

if __name__ == "__main__":
    main()
    