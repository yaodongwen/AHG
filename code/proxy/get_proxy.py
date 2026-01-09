import requests
import time

# ProxyPool 的 API 地址 (刚才 Docker 启动的)
PROXY_POOL_URL = 'http://localhost:5555/random'

def get_proxy():
    """从本地运行的 ProxyPool 获取一个高质量代理"""
    try:
        response = requests.get(PROXY_POOL_URL)
        if response.status_code == 200:
            return response.text.strip()
    except Exception:
        return None
    return None

def smart_request(url, max_retries=3):
    """
    智能请求函数：
    1. 优先尝试本机 IP (速度最快)
    2. 如果本机失败，从代理池获取 IP 重试
    """
    # --- 第1阶段：尝试本机直连 ---
    try:
        print(f"正在尝试本机直连: {url}")
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp # 成功，直接返回
    except Exception as e:
        print(f"本机直连失败: {e}")

    # --- 第2阶段：切换代理重试 ---
    for i in range(max_retries):
        proxy = get_proxy()
        if not proxy:
            print("警告：代理池为空或无法连接")
            time.sleep(2)
            continue
            
        print(f"切换代理重试 (第{i+1}次): {proxy}")
        
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        
        try:
            resp = requests.get(url, proxies=proxies, timeout=5)
            if resp.status_code == 200:
                return resp # 代理成功
        except Exception:
            # 如果这个代理也不行，ProxyPool 后台检测到后会自动给它扣分
            # 我们只需要继续循环拿下一个代理即可
            print(f"代理 {proxy} 失效，尝试下一个...")
            
    print("所有尝试均失败")
    return None

# --- 使用示例 ---
if __name__ == "__main__":
    # 假设你要抓取一个网页
    target = "http://httpbin.org/ip" 
    
    result = smart_request(target)
    
    if result:
        print("最终抓取成功:", result.text)