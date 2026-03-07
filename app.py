import streamlit as st
import datetime
import gspread
import holidays
import time
import re

# ==========================================
# 🛠️ 輔助小工具
# ==========================================
def time_to_float(t_str):
    if not t_str or ":" not in t_str: return 0
    h, m = map(int, t_str.split(":"))
    if h < 7: h += 24 
    return h + m/60.0

def float_to_time(f):
    h = int(f)
    m = int(round((f - h) * 60))
    if m == 60:
        h += 1; m = 0
    if h >= 24: h -= 24
    return f"{h:02d}:{m:02d}"

def get_duration(amt_str):
    match = re.search(r'(\d+)\s*[Hh]', str(amt_str))
    if match: return int(match.group(1))
    return -1 

def get_extension(ext_str):
    if not ext_str: return 0.0
    match = re.search(r'([\d\.]+)', str(ext_str))
    if match:
        return float(match.group(1))
    return 0.0

# ==========================================
# 🎯 魔法按鈕專屬動作 (Callback)
# ==========================================
def apply_recommended_time(new_time):
    st.session_state.input_time = new_time.replace(":", "")
    st.session_state.check_status = "success"
    st.session_state.check_msg = f"✅ 已為您一鍵切換至【{new_time}】！請繼續填寫下方客資。"
    st.session_state.rec_before = None
    st.session_state.rec_after = None

# ==========================================
# 🎯 訂位成功浮動視窗
# ==========================================
@st.dialog("🎉 訂位成功！")
def show_success_modal(date_str, time_str, name, people, phone, amount):
    st.error("🔔 **記得跟客人確定訂位時間**\n\n🚨 **並且提醒包廂保留十分鐘 逾時取消**", icon="⚠️")
    st.markdown(f"""
    * **時間:** {date_str} {time_str}
    * **姓名:** {name}
    * **人數:** {people}
    * **手機號碼:** {phone}
    * **消費金額:** {amount}
    """)
    if st.button("✅ 確認並關閉", use_container_width=True):
        for key in ["f_people", "f_amount", "f_name", "f_phone", "f_contact", "f_memo", "f_ext", "f_card"]:
            st.session_state[key] = ""
        st.session_state["f_is_spec"] = False
        st.rerun()

# ==========================================
# 網頁基礎設定與 Session State 狀態記憶
# ==========================================
st.set_page_config(page_title="賓士府前店 - 訂位系統", page_icon="🎤", layout="centered")

# ==========================================
# 🎨 網頁視覺美化 (修復隱形文字問題 2.0)
# ==========================================
page_bg_img = '''
<style>
/* 1. 大背景設定：藍紫高級漸層 */
.stApp {
    background: linear-gradient(135deg, #0f172a 0%, #1a2a6c 50%, #3b0764 100%);
    background-size: cover;
    background-attachment: fixed;
}

/* 2. 主畫面的標題與一般文字變白 */
h1, h2, h3, label, .stMarkdown p {
    color: #ffffff !important;
}
h1 { text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }

/* 3. 表單毛玻璃特效 */
div[data-testid="stForm"] {
    background-color: rgba(255, 255, 255, 0.08);
    border-radius: 15px;
    padding: 20px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.15);
}

/* 4. 按鈕：深藍色背景、白色文字 */
div.stButton > button {
    background-color: #1e3a8a !important; 
    border: 1px solid #60a5fa !important; 
}
div.stButton > button p, div.stButton > button span {
    color: #ffffff !important; 
    font-weight: bold !important;
}
div.stButton > button:hover {
    background-color: #2563eb !important; 
    border-color: #93c5fd !important;
}

/* 5. Checkbox(打勾方塊) 文字：強制變白 */
div[data-testid="stCheckbox"] p, div[data-testid="stCheckbox"] label {
    color: #ffffff !important;
}

/* 6. ✅ 提示框 (Alert) 終極修復：把警告、提示的文字改成純白色！ */
div[data-testid="stAlert"] p, div[data-testid="stAlert"] span {
    color: #ffffff !important; 
}

/* 7. 浮動視窗 (Dialog)：因為它是白底，裡面的字必須維持深灰色 */
div[data-testid="stDialog"] p, div[data-testid="stDialog"] li, div[data-testid="stDialog"] h2, div[data-testid="stDialog"] span {
    color: #1f2937 !important; 
}
/* 確保浮動視窗裡的「確認按鈕」是綠底白字 */
div[data-testid="stDialog"] div.stButton > button {
    background-color: #10b981 !important; 
    border: none !important;
}
div[data-testid="stDialog"] div.stButton > button p {
    color: #ffffff !important;
}
</style>
'''
st.markdown(page_bg_img, unsafe_allow_html=True)

st.title("🎤 賓士府前店 - 快速訂位系統")

if "input_time" not in st.session_state:
    st.session_state.input_time = "1800"
if "last_submit" not in st.session_state:
    st.session_state.last_submit = 0
if "check_msg" not in st.session_state:
    st.session_state.check_msg = None
if "check_status" not in st.session_state:
    st.session_state.check_status = None
if "rec_before" not in st.session_state:
    st.session_state.rec_before = None
if "rec_after" not in st.session_state:
    st.session_state.rec_after = None
if "available_vips" not in st.session_state:
    st.session_state.available_vips = []

# ==========================================
# ❶ 第一階段：查詢時段與包廂
# ==========================================
st.markdown("### ❶ 確認時段與包廂")
colA, colB, colC = st.columns(3)

tw_today = (datetime.datetime.now() + datetime.timedelta(hours=8)).date()

with colA:
    日期 = st.date_input("選擇日期", tw_today)
with colB:
    時間 = st.text_input("時間 (例如 1800)", key="input_time")
with colC:
    包廂選項 = st.selectbox("指定包廂", ["不指定", "小VIP", "大VIP(317)", "指定其他包廂"])
    自訂包廂號碼 = ""
    if 包廂選項 == "指定其他包廂":
        自訂包廂號碼 = st.text_input("輸入包廂號碼 (如: 201)")

# --- 🔍 查詢按鈕 ---
if st.button("🔍 檢查空位與包廂", use_container_width=True):
    if 包廂選項 == "指定其他包廂" and 自訂包廂號碼.strip() == "":
        st.error("❌ 請在上方輸入您想指定的「包廂號碼」再按查詢喔！")
        st.stop()
        
    st.info("🔄 系統查詢中，請稍候...")
    st.session_state.rec_before = None
    st.session_state.rec_after = None
    st.session_state.available_vips = [] 
    
    if len(時間) == 4 and ":" not in 時間:
        時間 = 時間[:2] + ":" + 時間[2:]
        
    hour = int(時間.split(":")[0])
    if 7 <= hour < 17: 班別 = "早班"
    elif 17 <= hour <= 23: 班別 = "中班"
    else: 班別 = "晚班" 

    weekdays_chinese = ["一", "二", "三", "四", "五", "六", "日"]
    file_date_str = f"{日期.month}/{日期.day}({weekdays_chinese[日期.weekday()]})"
    file_name = file_date_str + "訂位表"

    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sheet = gc.open(file_name).worksheet(班別)
        data = sheet.get_all_values()
        
        is_vip_conflict = False
        vip_conflict_msg = ""
        
        if 包廂選項 != "不指定":
            if 包廂選項 == "小VIP":
                target_rooms = ["101", "102", "103", "205", "305"]
                buffer_time = 1.0  
            elif 包廂選項 == "大VIP(317)":
                target_rooms = ["317"]
                buffer_time = 1.0  
            elif 包廂選項 == "指定其他包廂":
                target_rooms = [自訂包廂號碼.strip()]
                buffer_time = 0.5  
                
            req_start = time_to_float(時間)
            
            vip_status_msgs = []
            avail_vips = []

            for room_no in target_rooms:
                room_bookings = []
                current_time_tracker = "" 
                
                for r in data:
                    raw_time = str(r[2]).strip() if len(r) > 2 else ""
                    if raw_time and ":" in raw_time:
                        current_time_tracker = raw_time
                        
                    val_B = str(r[1]).strip() if len(r) > 1 else ""
                    val_L = str(r[11]).strip() if len(r) > 11 else ""
                    
                    if room_no in val_B or room_no in val_L:
                        b_time = current_time_tracker 
                        b_name = str(r[3]).strip() if len(r) > 3 else ""
                        if not b_time or ":" not in b_time: continue
                        
                        b_dur = get_duration(r[5] if len(r) > 5 else "")
                        b_ext = get_extension(r[9] if len(r) > 9 else "")
                        
                        if b_dur != -1:
                            b_dur += b_ext

                        b_start = time_to_float(b_time)
                        room_bookings.append({
                            'time_str': b_time, 'start': b_start, 'dur': b_dur, 'name': b_name
                        })
                
                room_bookings.sort(key=lambda x: x['start'])
                
                today_strs = []
                for b in room_bookings:
                    dur_str = f"({b['dur']:g}H)" if b['dur'] != -1 else "(無時數)"
                    today_strs.append(f"{b['time_str']} {b['name']}{dur_str}")
                today_info = "今日：" + "、".join(today_strs) if today_strs else "今日無訂位"
                
                timeline = []
                for b in room_bookings:
                    st_val = b['start']
                    ed_val = b['start'] + b['dur'] + buffer_time if b['dur'] != -1 else 48.0
                    timeline.append((st_val, ed_val, b))
                
                blocker = None
                for (st_val, ed_val, b) in timeline:
                    if req_start >= st_val - buffer_time and req_start < ed_val:
                        blocker = b
                        break
                
                if blocker:
                    rec_before = float_to_time(blocker['start'] - buffer_time)
                    t = blocker['start'] + blocker['dur'] + buffer_time if blocker['dur'] != -1 else 48.0
                    while True:
                        next_blocker = None
                        for (st_val, ed_val, b) in timeline:
                            if t >= st_val - buffer_time and t < ed_val:
                                next_blocker = (st_val, ed_val)
                                break
                        if not next_blocker: break
                        t = next_blocker[1]
                        if t >= 48.0: break
                    
                    rec_after = "需看訂位表" if t >= 48.0 else float_to_time(t)
                    tail_msg = f"往後可訂 **{rec_after}**" if rec_after != "需看訂位表" else "往後 **需看訂位表**"
                    
                    vip_status_msgs.append(f"⚠️ **【{room_no}】**：{today_info}\n👉 該時段不可訂！往前最晚可唱至 **{rec_before}**，{tail_msg}")
                else:
                    avail_vips.append(room_no)
                    next_b = None
                    for (st_val, ed_val, b) in timeline:
                        if st_val > req_start:
                            if not next_b or st_val < next_b['start']:
                                next_b = b
                    
                    if next_b:
                        hard_stop = float_to_time(next_b['start'] - buffer_time)
                        vip_status_msgs.append(f"✅ **【{room_no}】**：{today_info}\n👉 **可訂！**最晚可唱至 **{hard_stop}**")
                    else:
                        vip_status_msgs.append(f"✅ **【{room_no}】**：{today_info}\n👉 **空閒可訂！**")

            st.session_state.available_vips = avail_vips

            if len(avail_vips) > 0:
                is_vip_conflict = False
                vip_conflict_msg = "🎉 **查詢結果：指定包廂有空！**\n\n" + "\n\n".join(vip_status_msgs)
            else:
                is_vip_conflict = True
                vip_conflict_msg = "😭 **糟糕！指定的包廂皆已客滿！**\n\n" + "\n\n".join(vip_status_msgs)
        
        target_row_number = -1
        is_time_full = False
        booked_names = []
        requested_index = -1
        
        for index, row in enumerate(data):
            if len(row) > 3 and row[2] == 時間:
                requested_index = index
                if row[3] == "": 
                    target_row_number = index + 1 
                else:
                    booked_names.append(row[3]) 
                    check_idx = index + 1
                    while check_idx < len(data):
                        next_row = data[check_idx]
                        if len(next_row) > 3 and next_row[2] != "": break
                        if len(next_row) > 3 and next_row[2] == "":
                            if len(next_row) > 3 and next_row[3] == "": 
                                target_row_number = check_idx + 1
                                break
                            elif len(next_row) > 3 and next_row[3] != "":
                                booked_names.append(next_row[3]) 
                        check_idx += 1
                    
                    if target_row_number == -1:
                        is_time_full = True
                break
                
        if 包廂選項 != "不指定":
            if is_vip_conflict:
                st.session_state.check_status = "error"
                st.session_state.check_msg = vip_conflict_msg
            elif is_time_full:
                st.session_state.check_status = "warning"
                st.session_state.check_msg = vip_conflict_msg + "\n\n⚠️ **但是注意：【一般訂位表】的格子已經滿了，無法寫入資料！**"
            else:
                st.session_state.check_status = "success"
                st.session_state.check_msg = vip_conflict_msg + "\n\n👉 **請繼續填寫下方客資完成訂位！**"
        else:
            if is_time_full:
                booked_by = "、".join(booked_names)
                st.session_state.check_status = "warning"
                st.session_state.check_msg = f"⚠️ 糟糕！【{時間}】的一般包廂已經被「{booked_by}」全數訂滿了！"
                
                for i in range(requested_index - 1, -1, -1):
                    if len(data[i]) > 3 and ":" in data[i][2] and data[i][3] == "":
                        st.session_state.rec_before = data[i][2]; break
                for i in range(requested_index + 1, len(data)):
                    if len(data[i]) > 3 and ":" in data[i][2] and data[i][3] == "": 
                        st.session_state.rec_after = data[i][2]; break
            elif target_row_number != -1:
                st.session_state.check_status = "success"
                st.session_state.check_msg = f"✅ **【{時間}】目前還有位子！** 您可以繼續填寫下方資料完成訂位。"
            else:
                st.session_state.check_status = "warning"
                st.session_state.check_msg = f"❓ 找不到 {時間} 這個時間格子。"

    except Exception as e:
        st.error(f"❌ 查詢失敗 (請確認該日期檔案已建立)：{e}")

# --- 💬 顯示查詢結果與【互動按鈕】 ---
if st.session_state.check_msg:
    if st.session_state.check_status == "success": 
        st.success(st.session_state.check_msg)
    elif st.session_state.check_status == "warning": 
        st.warning(st.session_state.check_msg)
    else: 
        st.error(st.session_state.check_msg)

    if st.session_state.rec_before or st.session_state.rec_after:
        st.markdown("💡 **系統為您尋找最接近空位，請點擊按鈕直接帶入：**")
        col_btn1, col_btn2 = st.columns(2)
        
        if st.session_state.rec_before:
            col_btn1.button(
                f"⏱️ 直接改為 {st.session_state.rec_before}", 
                use_container_width=True,
                on_click=apply_recommended_time,
                args=(st.session_state.rec_before,)
            )
                
        if st.session_state.rec_after:
            col_btn2.button(
                f"⏱️ 直接改為 {st.session_state.rec_after}", 
                use_container_width=True,
                on_click=apply_recommended_time,
                args=(st.session_state.rec_after,)
            )

st.divider()

# ==========================================
# ❷ 第二階段：填寫客資與送出 
# ==========================================
st.markdown("### ❷ 填寫客資並送出")
with st.form("booking_form"):
    col1, col2 = st.columns(2)
    with col1:
        人數 = st.text_input("人數", placeholder="例如：4", key="f_people")
        消費金額 = st.text_input("消費金額 (請包含時數)", placeholder="例如：4099/5H", key="f_amount")
        姓名 = st.text_input("姓名", placeholder="例如：王大明", key="f_name")
        聯絡電話 = st.text_input("聯絡電話", placeholder="例如：0912345678", key="f_phone")
    with col2:
        接洽人 = st.text_input("接洽人", placeholder="例如：軒", key="f_contact")
        備註 = st.text_input("備註 (沒有可留白)", placeholder="例如：可換/未匯訂", key="f_memo")
        續時 = st.text_input("續時 (沒有可留白)", placeholder="例如：1", key="f_ext")
        卡號 = st.text_input("卡號 (沒有可留白)", placeholder="例如：11572", key="f_card")
        
        if 包廂選項 == "小VIP":
            options = st.session_state.available_vips if st.session_state.available_vips else ["101", "102", "103", "205", "305"]
            實際包廂 = st.selectbox("👉 請選擇要安排哪一間", options)
        elif 包廂選項 == "大VIP(317)":
            實際包廂 = "317"
            st.info(f"👉 將為您安排包廂：317")
        elif 包廂選項 == "指定其他包廂":
            實際包廂 = 自訂包廂號碼.strip()
            if 實際包廂:
                st.info(f"👉 將為您安排指定包廂：{實際包廂}")
        else:
            實際包廂 = ""

    是否指定包廂 = st.checkbox("🎯 標記為『指定包廂』 (打勾後會在表單包廂號碼前加上『指』字防誤刪)", key="f_is_spec")

    submitted = st.form_submit_button("🚀 確認送出訂位", use_container_width=True)

if submitted:
    current_time = time.time()
    if current_time - st.session_state.last_submit < 3:
        st.error("⏳ 系統處理中，請勿連續點擊！（防重複訂位機制已啟動）")
        st.stop()
    st.session_state.last_submit = current_time

    if 姓名 == "":
        st.error("❌ 訂位失敗：請輸入客人「姓名」喔！(請重新填寫送出)")
        st.stop()

    st.info("🔄 正在寫入雲端表單，請稍候...")
    try:
        確認時間 = st.session_state.input_time 
        if len(確認時間) == 4 and ":" not in 確認時間: 
            確認時間 = 確認時間[:2] + ":" + 確認時間[2:]
            
        hour = int(確認時間.split(":")[0])
        if 7 <= hour < 17: 班別 = "早班"
        elif 17 <= hour <= 23: 班別 = "中班"
        else: 班別 = "晚班" 

        weekdays_chinese = ["一", "二", "三", "四", "五", "六", "日"]
        file_date_str = f"{日期.month}/{日期.day}({weekdays_chinese[日期.weekday()]})"
        file_name = file_date_str + "訂位表"

        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sheet = gc.open(file_name).worksheet(班別)
        data = sheet.get_all_values()
        
        target_row_number = -1
        for index, row in enumerate(data):
            if len(row) > 3 and row[2] == 確認時間:
                if row[3] == "": 
                    target_row_number = index + 1 
                else:
                    check_idx = index + 1
                    while check_idx < len(data):
                        next_row = data[check_idx]
                        if len(next_row) > 3 and next_row[2] != "": break
                        if len(next_row) > 3 and next_row[2] == "":
                            if len(next_row) > 3 and next_row[3] == "": 
                                target_row_number = check_idx + 1
                                break
                        check_idx += 1
                break 

        if target_row_number != -1:
            tw_now = datetime.datetime.now() + datetime.timedelta(hours=8)
            接洽人_寫入 = f"{接洽人}{tw_now.month}/{tw_now.day}" if 接洽人.strip() != "" else ""

            cell_range_data = f"D{target_row_number}:K{target_row_number}"
            update_values_data = [[姓名, 人數, 消費金額, 聯絡電話, 卡號, 接洽人_寫入, 續時, 備註]]
            sheet.update(range_name=cell_range_data, values=update_values_data)
            
            實際包廂_寫入 = 實際包廂
            if 實際包廂 != "":
                if 是否指定包廂:
                    實際包廂_寫入 = f"指{實際包廂}"
                sheet.update(range_name=f"B{target_row_number}", values=[[實際包廂_寫入]])
                
                try:
                    if 包廂選項 in ["小VIP", "大VIP(317)"]:
                        sheet.format(f"B{target_row_number}", {
                            "backgroundColor": {
                                "red": 0.0,
                                "green": 1.0,
                                "blue": 0.0
                            }
                        })
                    else:
                        sheet.format(f"B{target_row_number}", {
                            "backgroundColor": {
                                "red": 1.0,
                                "green": 1.0,
                                "blue": 1.0
                            }
                        })
                except Exception:
                    pass 

            st.balloons()
            st.session_state.check_msg = None
            st.session_state.check_status = None
            
            show_success_modal(file_date_str, 確認時間, 姓名, 人數, 聯絡電話, 消費金額)
            
        else:
            st.error(f"⚠️ 寫入失敗！包廂有空，但 Google 訂位表上【{確認時間}】的『格子已經滿了』寫不下了！\n\n💡 解決方法：請改選前後 10 分鐘的空檔送出，或前往 Google 表單手動插入空白行。")

    except Exception as e:
        st.error(f"❌ 發生未知的錯誤：{e}")