import akshare as ak
import pandas as pd
import time
import os

def get_concept_stocks(keywords):
    """
    根据关键词获取概念成分股（基于东方财富数据源）
    """
    print("正在初始化概念列表，请稍候...")
    try:
        # 获取所有概念板块列表
        # 东方财富的概念板块数据比较全
        concept_list = ak.stock_board_concept_name_em()
    except Exception as e:
        print(f"获取概念列表失败，请检查网络或AkShare版本。错误: {e}")
        return

    # 创建结果文件夹
    output_dir = "concept_data"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for keyword in keywords:
        print(f"\n-------- 正在搜索关键词: {keyword} --------")
        
        # 1. 模糊匹配概念名称
        # 在所有概念中找到包含 keyword 的行
        match_concepts = concept_list[concept_list['板块名称'].str.contains(keyword)]
        
        if match_concepts.empty:
            print(f"  [X] 未找到包含 '{keyword}' 的概念板块。")
            continue
            
        # 2. 遍历匹配到的每一个具体概念
        for index, row in match_concepts.iterrows():
            board_name = row['板块名称']
            board_code = row['板块代码'] # 实际上akshare这个接口主要靠name调用，但保留code备用
            
            print(f"  -> 发现概念: {board_name}，正在获取成分股...")
            
            try:
                # 获取该概念下的成分股
                stock_df = ak.stock_board_concept_cons_em(symbol=board_name)
                
                # 3. 数据清洗（保留常用字段）
                # 通常包含: 代码, 名称, 最新价, 涨跌幅等
                if not stock_df.empty:
                    save_name = f"{board_name}.csv"
                    save_path = os.path.join(output_dir, save_name)
                    
                    # 4. 保存文件 (Mac Excel友好格式)
                    stock_df.to_csv(save_path, index=False, encoding='utf-8-sig')
                    print(f"     [√] 已保存: {save_path} (共 {len(stock_df)} 只股票)")
                else:
                    print(f"     [!] 概念 {board_name} 无成分股数据。")
                
                # 礼貌性延时，防止被封IP
                time.sleep(1.5)
                
            except Exception as e:
                print(f"     [!] 获取 {board_name} 数据失败: {e}")

if __name__ == "__main__":
    # === 在这里修改你想查找的关键词 ===
    # 注意：这里主要获取的是 A股 关联的概念股
    MY_KEYWORDS = ["英伟达", "特斯拉", "算力", "Sora"]
    
    get_concept_stocks(MY_KEYWORDS)
    print("\n所有任务完成。请查看 concept_data 文件夹。")