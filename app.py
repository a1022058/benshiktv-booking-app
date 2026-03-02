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
    # 如果有打幾 H 就抓出來，如果沒打 (例如董事之友)，就回傳 -1 代表未知長度
    match = re.search(r'(\d+)\s*[Hh]', str(amt_str))
    if match: return int(match.group(1))
    return -1 

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
# 網頁基礎設定與 Session State 狀態記憶
# ==========================================
st.set_page_config(page_title="賓士府前店 - 訂位系統", page_icon="🎤", layout="centered")
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
with colA:
    日期 = st.date_input("選擇日期", datetime.date.today())
with colB:
    時間 = st.text_input("時間 (例如 1800)", key="input_time")
with colC:
    包廂 = st.selectbox("指定VIP包廂", ["不指定", "小VIP", "大VIP(317)"])

# --- 🔍 查詢按鈕 ---
if st.button("🔍 檢查空位與包廂", use_container_width=True):
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
        
        # ==========================================
        # 🛡️ 【全天候透視版】VIP 包廂群組掃描防撞
        # ==========================================
        if 包廂 != "不指定":
            target_rooms = ["101", "102", "103", "205", "305"] if 包廂 == "小VIP" else ["317"]
            req_start = time_to_float(時間)
            
            vip_status_msgs = []
            avail_vips = []

            for room_no in target_rooms:
                room_bookings = []
                # 1. 把這個包廂今天「所有」的訂位都抓出來
                for r in data:
                    val_B = str(r[1]).strip() if len(r) > 1 else ""
                    val_L = str(r[11]).strip() if len(r) > 11 else ""
                    
                    if room_no in val_B or room_no in val_L:
                        b_time = r[2]
                        b_name = r[3]
                        if not b_time or ":" not in b_time: continue
                        
                        b_dur = get_duration(r[5] if len(r) > 5 else "")
                        b_start = time_to_float(b_time)
                        room_bookings.append({
                            'time_str': b_time, 'start': b_start, 'dur': b_dur, 'name': b_name
                        })
                
                # 照時間先後排好
                room_bookings.sort(key=lambda x: x['start'])
                
                # 2. 檢查你查的這個時間 (req_start) 有沒有跟別人「直接撞到」
                conflicting_booking = None
                for b in room_bookings:
                    # 如果時數未知 (-1)，就當作他唱到打烊 (設定個超大數字 48.0)
                    b_end = b['start'] + b['dur'] + 1 if b['dur'] != -1 else 48.0 
                    
                    # 情況A：剛好落在別人唱的時間內
                    if b['start'] <= req_start < b_end:
                        conflicting_booking = b
                        break
                    # 情況B：你想訂的時間比別人早，但剩下的時間根本不夠唱 (連1小時都不到)
                    elif req_start < b['start'] and (b['start'] - req_start - 1) <= 0:
                        conflicting_booking = b
                        break

                if conflicting_booking:
                    # 💥 直接撞場了！(顯示紅/黃燈警告)
                    b = conflicting_booking
                    rec_before = float_to_time(b['start'] - 1)
                    b_end_str = float_to_time(b['start'] + b['dur'] + 1) if b['dur'] != -1 else "需看訂位表"
                    dur_text = f" (預計唱 {b['dur']}H)" if b['dur'] != -1 else ""
                    
                    tail_msg = f"可訂 **{b_end_str}**" if b_end_str != "需看訂位表" else "**需看訂位表**"
                    vip_status_msgs.append(f"⚠️ **【{room_no}】**：{b['time_str']} 已有「{b['name']}」訂位{dur_text} 👉 往前最晚可唱至 **{rec_before}**，往後 {tail_msg}")
                else:
                    # 🎉 沒有直接撞場！(顯示綠燈，但要幫忙看後面有沒有人)
                    next_bookings = [b for b in room_bookings if b['start'] > req_start]
                    if next_bookings:
                        # 後面還有人！
                        next_b = next_bookings[0]
                        hard_stop = float_to_time(next_b['start'] - 1)
                        b_end_str = float_to_time(next_b['start'] + next_b['dur'] + 1) if next_b['dur'] != -1 else "需看訂位表"
                        
                        tail_msg = f"可訂 **{b_end_str}**" if b_end_str != "需看訂位表" else "**需看訂位表**"
                        vip_status_msgs.append(f"✅ **【{room_no}】**：{next_b['time_str']} 已有「{next_b['name']}」訂位！最晚可唱至 **{hard_stop}**，往後 {tail_msg}")
                    else:
                        # 今天後面都沒人了！
                        vip_status_msgs.append(f"✅ **【{room_no}】**：空閒可訂！")
                    
                    # 只要沒有「直接撞場」，這個包廂就能列入可選擇清單
                    avail_vips.append(room_no)

            st.session_state.available_vips = avail_vips

            if len(avail_vips) > 0:
                is_vip_conflict = False
                vip_conflict_msg = "🎉 **查詢結果：有空包廂！**\n\n" + "\n\n".join(vip_status_msgs)
            else:
                is_vip_conflict = True
                vip_conflict_msg = "😭 **糟糕！該時段的VIP包廂皆已客滿！**\n\n" + "\n\n".join(vip_status_msgs)
        
        # 🛡️ 一般時段客滿檢查
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
                
        # 產生存檔結果 
        if 包廂 != "不指定":
            if is_vip_conflict:
                st.session_state.check_status = "error"
                st.session_state.check_msg = vip_conflict_msg
            elif is_time_full:
                st.session_state.check_status = "warning"
                st.session_state.check_msg = vip_conflict_msg + "\n\n⚠️ **但是注意：【一般訂位表】的格子已經滿了，無法寫入資料！**"
            else:
                st.session_state.check_status = "success"
                st.session_state.check_msg = vip_conflict_msg + "\n\n👉 **請繼續填寫下方客資完成訂位，並選擇要分配哪一間！**"
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
        人數 = st.text_input("人數", placeholder="例如：4")
        消費金額 = st.text_input("消費金額 (請包含時數)", placeholder="例如：4099/5H")
        姓名 = st.text_input("姓名", placeholder="例如：王大明")
        聯絡電話 = st.text_input("聯絡電話", placeholder="例如：0912345678")
    with col2:
        接洽人 = st.text_input("接洽人", placeholder="例如：軒")
        備註 = st.text_input("備註 (沒有可留白)", placeholder="例如：可換/未匯訂")
        續時 = st.text_input("續時 (沒有可留白)", placeholder="例如：1")
        卡號 = st.text_input("卡號 (沒有可留白)", placeholder="例如：11572")
        
        if 包廂 == "小VIP":
            options = st.session_state.available_vips if st.session_state.available_vips else ["101", "102", "103", "205", "305"]
            實際包廂 = st.selectbox("👉 請選擇要安排哪一間", options)
        elif 包廂 == "大VIP(317)":
            實際包廂 = "317"
        else:
            實際包廂 = ""

    submitted = st.form_submit_button("🚀 確認送出訂位", use_container_width=True)

if submitted:
    current_time = time.time()
    if current_time - st.session_state.last_submit < 3:
        st.error("⏳ 系統處理中，請勿連續點擊！（防重複訂位機制已啟動）")
        st.stop()
    st.session_state.last_submit = current_time

    if 姓名 == "":
        st.error("❌ 訂位失敗：請輸入客人「姓名」喔！")
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
            
            if 實際包廂 != "":
                sheet.update(range_name=f"B{target_row_number}", values=[[實際包廂]])

            st.success(f"🎉 **訂位成功！**👉 已為「**{姓名}**」保留 **{確認時間}** 的包廂。")
            st.balloons()
            
            st.session_state.check_msg = None
            st.session_state.check_status = None
        else:
            st.error(f"⚠️ 糟糕！您填寫資料的這段期間，【{確認時間}】的空位被搶走或有衝突了！請重新查詢。")

    except Exception as e:
        st.error(f"❌ 發生未知的錯誤：{e}")