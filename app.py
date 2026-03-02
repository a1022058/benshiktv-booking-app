import streamlit as st
import datetime
import gspread
import holidays

# 網頁標題與圖示設定
st.set_page_config(page_title="賓士府前店 - 訂位系統", page_icon="🎤", layout="centered")
st.title("🎤 賓士府前店 - 快速訂位系統")

# 建立一個表單介面 (這樣才不會打一個字系統就重跑一次)
with st.form("booking_form"):
    st.markdown("### 📋 訂位資料填寫")
    執行動作 = st.radio("請選擇執行動作：", ["🔍 查詢空位", "📝 直接訂位"], horizontal=True)
    
    # 用雙欄位排版，讓網頁看起來更專業
    col1, col2 = st.columns(2)
    with col1:
        日期 = st.date_input("選擇日期", datetime.date.today())
        時間 = st.text_input("時間 (例如 1800 或 18:20)", value="1800")
        人數 = st.text_input("人數", placeholder="例如：4")
        聯絡電話 = st.text_input("聯絡電話", placeholder="例如：0912345678")
        續時 = st.text_input("續時 (沒有可留白)", placeholder="例如：1")
        
    with col2:
        姓名 = st.text_input("姓名", placeholder="例如：王大明")
        消費金額 = st.text_input("消費金額", placeholder="例如：1000/3H")
        卡號 = st.text_input("卡號 (沒有可留白)", placeholder="例如：11572")
        接洽人 = st.text_input("接洽人", placeholder="例如：小薇")
        備註 = st.text_input("備註 (沒有可留白)", placeholder="例如：可換/未匯訂")

    # 送出按鈕
    submitted = st.form_submit_button("🚀 送出執行")

# ==========================================
# 只要按下「送出」按鈕，就會開始執行下面的引擎
# ==========================================
if submitted:
    st.divider() # 畫一條分隔線
    st.info("🔄 系統處理中，請稍候...")
    
    try:
        # --- 處理時間格式 ---
        if len(時間) == 4 and ":" not in 時間:
            時間 = 時間[:2] + ":" + 時間[2:]
            
        hour = int(時間.split(":")[0])
        if 7 <= hour < 17:
            班別 = "早班"
        elif 17 <= hour <= 23:
            班別 = "中班"
        else:
            班別 = "晚班" 
            
        # --- 🛡️ 30 天訂位限制雷達 ---
        tw_now = datetime.datetime.now() + datetime.timedelta(hours=8)
        today = tw_now.replace(hour=0, minute=0, second=0, microsecond=0)
        # st.date_input 產生的日期本來就是 date 格式，所以直接拿來算
        diff_days = (日期 - today.date()).days
        
        if diff_days > 30:
            st.error(f"🚫 **系統阻擋：這筆訂位是 {diff_days} 天後！**\n\n💡 提醒：店內規定只開放 30 天內的訂位喔！請重選日期。")
            st.stop() # 讓程式立刻停在這裡

        weekdays_chinese = ["一", "二", "三", "四", "五", "六", "日"]
        weekday_str = weekdays_chinese[日期.weekday()]
        file_date_str = f"{日期.month}/{日期.day}({weekday_str})"
        file_name = file_date_str + "訂位表"

        # --- 💰 台灣國定假日計費雷達 ---
        tw_holidays = holidays.TW()
        tomorrow = 日期 + datetime.timedelta(days=1)
        
        is_today_holiday = 日期 in tw_holidays
        is_tomorrow_holiday = tomorrow in tw_holidays
        is_tomorrow_weekend = tomorrow.weekday() >= 5 
        
        if is_today_holiday:
            holiday_name = tw_holidays.get(日期)
            if not is_tomorrow_holiday and not is_tomorrow_weekend:
                st.warning(f"💰 **計費提醒：【{holiday_name} 最後一天】🚨 全日比照週日消費！**")
            else:
                st.warning(f"💰 **計費提醒：【{holiday_name} 連假】🚨 全日比照週六消費！**")
        elif is_tomorrow_holiday:
            holiday_name = tw_holidays.get(tomorrow)
            if hour >= 17:
                st.warning(f"💰 **計費提醒：【{holiday_name} 前夕】🚨 17:00 後比照週五消費！**")
            else:
                st.warning(f"💰 **計費提醒：【{holiday_name} 前夕】白天仍為平日，17:00後比照週五！**")
        elif weekday_str == "五" and hour >= 17:
            st.warning("💰 **計費提醒：【週五小週末】🚨 17:00 後比照週末消費！**")
        elif weekday_str == "六":
            st.warning("💰 **計費提醒：【週末】🚨 全日為週末消費！**")
        elif weekday_str == "日":
            if hour < 17:
                st.warning("💰 **計費提醒：【週日白天】🚨 16:59 前為週末消費！**")
            else:
                st.info("💰 計費提醒：【週日晚上】目前為平日消費時段。")
        else:
            st.info("💰 計費提醒：目前為平日消費時段。")

        # --- 🔑 登入 Google 雲端 (使用 Streamlit 機密金鑰) ---
        # 這裡的寫法跟 Colab 不一樣囉！它是靠我們之後要在後台貼上的 JSON 金鑰來登入
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        
        # --- 開啟表單 ---
        try:
            sheet = gc.open(file_name).worksheet(班別)
            data = sheet.get_all_values()
        except gspread.exceptions.SpreadsheetNotFound:
            st.error(f"❌ **找不到檔案：** 雲端硬碟裡沒有叫做「{file_name}」的檔案！\n\n(如果這是未來的日期，請確認店長已經新增了該日期的訂位表，並共用給機器人喔！)")
            st.stop()
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ **找不到分頁：** 檔案「{file_name}」裡面沒有叫做「{班別}」的分頁！")
            st.stop()
        
        target_row_number = -1
        is_booked = False
        requested_index = -1 
        booked_names = [] 
        
        # --- 尋找空位與合併儲存格邏輯 ---
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
                        if len(next_row) > 3 and next_row[2] != "":
                            break
                        if len(next_row) > 3 and next_row[2] == "":
                            if len(next_row) > 3 and next_row[3] == "": 
                                target_row_number = check_idx + 1
                                break
                            elif len(next_row) > 3 and next_row[3] != "":
                                booked_names.append(next_row[3]) 
                        check_idx += 1
                    
                    if target_row_number == -1:
                        is_booked = True
                        booked_by = "、".join(booked_names)
                break 

        # --- 執行動作判斷 ---
        if 執行動作 == "🔍 查詢空位":
            st.write(f"🔍 正在為您查詢：**{file_date_str} {班別} {時間}**")
            if target_row_number != -1:
                st.success(f"✅ **【{時間}】目前還有空包廂！** 您可以切換為「📝 直接訂位」輸入客人資料了。")
            elif is_booked:
                st.error(f"⚠️ 糟糕！【{時間}】的包廂已經被「{booked_by}」全數訂滿了！")
            else:
                st.warning(f"❓ 找不到 {時間} 這個時間格子。")
                
        elif 執行動作 == "📝 直接訂位":
            if 姓名 == "":
                st.error("❌ 訂位失敗：請輸入客人「姓名」喔！")
            elif target_row_number != -1:
                cell_range = f"D{target_row_number}:K{target_row_number}"
                update_values = [[姓名, 人數, 消費金額, 聯絡電話, 卡號, 接洽人, 續時, 備註]]
                sheet.update(range_name=cell_range, values=update_values)
                st.success(f"🎉 **訂位成功！**\n\n👉 **【{file_date_str} {班別} {時間}】** 已為「**{姓名}**」保留包廂。")
                st.balloons() # 成功的話，網頁會噴出氣球特效！🎈
            elif is_booked:
                st.error(f"⚠️ 糟糕！【{時間}】的包廂已經被「{booked_by}」全數訂滿了！無法寫入。")
            else:
                st.warning(f"❓ 找不到 {時間} 這個時間格子。")

        # --- 候補推薦系統 ---
        if is_booked:
            st.markdown("### 💡 系統為您尋找最接近的空位：")
            nearest_before = None
            nearest_after = None
            
            for i in range(requested_index - 1, -1, -1):
                row = data[i]
                if len(row) > 3 and ":" in row[2] and row[3] == "":
                    nearest_before = row[2]
                    break
                        
            for i in range(requested_index + 1, len(data)):
                row = data[i]
                if len(row) > 3 and ":" in row[2] and row[3] == "": 
                    nearest_after = row[2]
                    break
                        
            if nearest_before: 
                st.write(f"⬆️ 往前最快：**【{nearest_before}】**還有空位")
            if nearest_after: 
                st.write(f"⬇️ 往後最快：**【{nearest_after}】**還有空位")
            if not nearest_before and not nearest_after: 
                st.write("😭 抱歉，這個班別已經全滿了！")

    except ValueError:
        st.error("❌ 發生錯誤：請確定時間格式有打對（例如 1800 或 18:00）")
    except Exception as e:
        st.error(f"❌ 發生未知的錯誤，詳細原因：{e}")