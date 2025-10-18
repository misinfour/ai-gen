import requests

def kv_read(account_id: str, namespace_id: str, api_token: str, key: str):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}"
    headers = {
        "Authorization": f"Bearer {api_token}",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    elif response.status_code == 404:
        return None
    elif response.status_code == 401 or response.status_code == 403:
        return {"error": "Authentication failed. Check API token and permissions."}
    else:
        try:
            return response.json()
        except Exception:
            return {"error": response.text, "status": response.status_code}

def kv_write(account_id: str, namespace_id: str, api_token: str, key: str, value: str):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "text/plain",
    }
    response = requests.put(url, headers=headers, data=value)
    if response.status_code == 200:
        return {"success": True}
    elif response.status_code == 401 or response.status_code == 403:
        return {"success": False, "error": "Authentication failed. Check API token and permissions."}
    else:
        try:
            return response.json()
        except Exception:
            return {"error": response.text, "status": response.status_code}

def kv_delete(account_id: str, namespace_id: str, api_token: str, key: str):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}"
    headers = {
        "Authorization": f"Bearer {api_token}",
    }
    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        return {"success": True}
    elif response.status_code == 404:
        return {"success": False, "error": "Key not found"}
    elif response.status_code == 401 or response.status_code == 403:
        return {"success": False, "error": "Authentication failed. Check API token and permissions."}
    else:
        try:
            return response.json()
        except Exception:
            return {"error": response.text, "status": response.status_code}

# =====================
# 示例测试（已注释）
# =====================
# ACCOUNT_ID = "7f568267018e374a7cfdc6cde299e7ee"   # 确认无多余字符
# NAMESPACE_ID = "c681abe2d69d4e90832414969bf4f459"
# API_TOKEN = "xnQ_Roo-hQKnSHuewbI5wyekALaege1HxvOlgztv"

# # 写入 KV
# write_result = kv_write(ACCOUNT_ID, NAMESPACE_ID, API_TOKEN, "test", "hello world")
# print("写入结果:", write_result)

# # 读取 KV
# read_result = kv_read(ACCOUNT_ID, NAMESPACE_ID, API_TOKEN, "test")
# print("读取结果:", read_result)

# # 删除 KV
# delete_result = kv_delete(ACCOUNT_ID, NAMESPACE_ID, API_TOKEN, "test")
# print("删除结果:", delete_result)
