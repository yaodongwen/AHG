import akshare as ak
import pandas as pd
import time
import random
import os
from tqdm import tqdm  # 进度条库

def get_all_concepts_stocks():
    # 1. 设置保存路径
    base_dir = "../../concept"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    
    print("正在连接数据源，获取最新的概念板块列表...")
    
    try:
        # 获取所有概念板块的列表（名称和代码）
        concept_board_list = ak.stock_board_concept_name_em()
        # 清洗数据，去掉空值
        concept_board_list = concept_board_list[concept_board_list['板块名称'].notna()]
        
        total_concepts = len(concept_board_list)
        print(f"成功获取概念列表！共发现 {total_concepts} 个概念板块。")
        print("准备开始批量下载... (为防止封IP，每条下载会有随机延时)")
        
    except Exception as e:
        print(f"初始化失败，请检查网络或更新AkShare: {e}")
        return

    # 2. 遍历所有概念（使用tqdm显示进度条）
    # iterrows 性能一般，但对于几百行数据完全够用
    for index, row in tqdm(concept_board_list.iterrows(), total=total_concepts, unit="概念"):
        board_name = row['板块名称']
        
        # 这里的符号通常不需要，因为em接口主要靠中文名，但保留备用
        # board_code = row['板块代码'] 
        
        file_path = os.path.join(base_dir, f"{board_name}.xlsx")
        
        # 断点续传：如果文件已经存在，就跳过（防止程序中途报错断掉后要重头来）
        if os.path.exists(file_path):
            continue

        try:
            # 3. 获取具体成分股
            stock_df = ak.stock_board_concept_cons_em(symbol=board_name)
            
            if not stock_df.empty:
                # 4. 筛选和重命名字段 (只保留最有用的)
                # 原始字段通常有: 序号, 代码, 名称, 最新价, 涨跌幅, ...
                cols_to_keep = ['代码', '名称', '最新价', '涨跌幅', '换手率']
                # 确保字段存在再筛选，防止报错
                valid_cols = [c for c in cols_to_keep if c in stock_df.columns]
                final_df = stock_df[valid_cols]
                
                # 5. 保存为 Excel (xlsx)，Mac下Excel打开更友好，不会乱码
                final_df.to_excel(file_path, index=False)
            
            # === 关键：随机延时 3 到 6 秒 ===
            # 不要为了快把这个改小，否则你的IP会被东方财富封禁几个小时
            time.sleep(random.uniform(3, 6))
            
        except Exception as e:
            # 记录错误但不停止程序
            print(f"\n[Error] 获取 {board_name} 失败: {e}")
            time.sleep(5) # 出错后多休息一会

if __name__ == "__main__":
    print("=== 全量概念股爬虫启动 (Mac优化版) ===")
    get_all_concepts_stocks()
    print("\n所有任务已完成！请查看 'All_Concepts_Data' 文件夹。")