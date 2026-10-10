# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (c) 2026 lurenjiamax
"""Small runtime catalog for the three supported interface languages."""
from PyQt6.QtCore import QLocale
from PyQt6.QtWidgets import QLabel as QtLabel, QPushButton as QtButton

LANGUAGE = 'en'
# Source | English | Simplified Chinese. Traditional Chinese is the source.
ROWS = '''
返回鍵 + 首頁鍵|Back button + Home button|返回键 + 主页键
重置觸控驅動|Reset touchscreen driver|重置触控驱动
配置釋放|Release configuration|配置释放
配置接管|Take over configuration|配置接管
中控 CPU|Panel CPU|中控 CPU
跟隨系統|System default|跟随系统
僅小核|Little cores only|仅小核
僅限制中控應用；外部啟動的應用不受限制。|Limits only the panel; externally launched apps are unrestricted.|仅限制中控应用；外部启动的应用不受限制。
關於|About|关于
版本|Version|版本
原始碼|Source code|源代码
效能策略|Performance profile|性能 profile
風扇曲線|Fan curve|风扇曲线
目前僅支援並測試過 AYN Thor（Thorch BSP）；未來將擴展其他掌機。|Currently supported and tested only on AYN Thor with the Thorch BSP; other handhelds are planned.|目前仅支持并测试过 AYN Thor（Thorch BSP）；未来将扩展其他掌机。
原創程式碼：LGPL-3.0-or-later。第三方元件保留各自授權；Lucide 圖示採 ISC，PyQt6 採 GPL／商業授權。|Original code: LGPL-3.0-or-later. Third-party components retain their licenses; Lucide icons use ISC and PyQt6 uses GPL/commercial licensing.|原创代码：LGPL-3.0-or-later。第三方组件保留各自授权；Lucide 图标采用 ISC，PyQt6 采用 GPL／商业授权。
© 2026 lurenjiamax。本程式按現狀提供，不附任何擔保。|© 2026 lurenjiamax. Provided as-is, without warranty.|© 2026 lurenjiamax。本程序按现状提供，不附任何担保。
功率|Power|功率
快充|Fast charging|快充
充電功率|Charging|充电功率
功率消耗|Power draw|功率消耗
主屏|Top|主屏
副屏|Bottom|副屏
雙屏|Both|双屏
移動目前應用|Move current app|移动当前应用
新應用：上屏|New apps: top|新应用：上屏
新應用：下屏|New apps: bottom|新应用：下屏
Boost 關閉|Boost off|Boost 关闭
Boost 開啟|Boost on|Boost 开启
取消靜音|Unmute|取消静音
X：最低／最高亮度；Y：響應靈敏度。|X: minimum/maximum brightness; Y: sensitivity.|X：最低／最高亮度；Y：响应灵敏度。
讀寫掛載|Mount read/write|读写挂载
已掛載|Mounted|已挂载
尚未掛載|Not mounted|尚未挂载
解鎖後端已就緒|Unlock backend ready|解锁后端已就绪
需要匹配核心、原始金鑰與解鎖後端|Matching kernel, original keys and unlock backend required|需要匹配内核、原始密钥与解锁后端
手柄焦點|Gamepad focus|手柄焦点
自動切換|Automatic|自动切换
鎖定上屏|Lock top screen|锁定上屏
鎖定下屏|Lock bottom screen|锁定下屏
控制桌面焦點，不能隔離自行讀取手柄的應用。|Controls desktop focus; apps reading gamepad devices directly are not isolated.|控制桌面焦点，不能隔离自行读取手柄的应用。
上屏遮黑|Top screen blanked|上屏遮黑
下屏遮黑|Bottom screen blanked|下屏遮黑
CPU7 可能增加功耗，實際性能取決於負載。|CPU7 may increase power use; performance depends on the workload.|CPU7 可能增加功耗，实际性能取决于负载。
上屏顯示|Top screen visible|上屏显示
下屏顯示|Bottom screen visible|下屏显示
屏幕遮黑|Screen blanked|屏幕遮黑
UFS 中斷位置|UFS interrupt affinity|UFS 中断位置
恢復原配置|Restore original|恢复原配置
省電 CPU0–2|Power saving CPU0–2|省电 CPU0–2
高性能 CPU7|Performance CPU7|高性能 CPU7
允許 CPU|Allowed CPUs|允许 CPU
實際 CPU|Effective CPUs|实际 CPU
找不到 UFS 中斷|No UFS interrupt found|找不到 UFS 中断
進階數值面板|Advanced values|高级数值面板
編輯為自訂|Edit as custom|编辑为自定义
風扇聯動|Fan linkage|风扇联动
隨效能|Follow performance|随性能
獨立調節|Independent|独立调节
TAB 管理|Tab management|TAB 管理
常駐|Pinned|常驻
開啟|Open|打开
觸控板|Touchpad|触控板
左鍵|Left click|左键
右鍵|Right click|右键
下屏觸控板 → 上屏鼠標|Bottom touchpad → top-screen pointer|下屏触控板 → 上屏鼠标
單指移動／輕點左鍵；雙指滾動／輕點右鍵。光標限制在上屏。|One finger: move / tap to click. Two fingers: scroll / tap for right click. Pointer stays on the top screen.|单指移动／轻点左键；双指滚动／轻点右键。光标限制在上屏。
選擇常駐頁面；其他頁面可從此處開啟，離開後自動收起。設定頁始終保留。|Pin your tabs. Open other pages here; they close when you leave. Settings always remains available.|选择常驻页面；其他页面可从此处开启，离开后自动收起。设置页始终保留。
找不到上屏鼠標接口|Top-screen pointer interface is unavailable|找不到上屏鼠标接口
輸入模式|Input mode|输入模式
手柄模式|Gamepad mode|手柄模式
鼠標模式|Mouse mode|鼠标模式
高|High|高
低|Low|低
X：最低／最高亮度；Y：響應靈敏度（S）。音量自動歸一化，保留左右聲道差異。|X: minimum/maximum brightness. Y: response sensitivity (S). Audio auto-normalizes while preserving stereo balance.|X：最低／最高亮度；Y：响应灵敏度（S）。音量自动归一化，保留左右声道差异。
點擊預覽或按 L3／R3 開啟色環，轉動對應搖杆逐格選色，再按一次關閉。|Tap a preview or press L3/R3 to open the dial. Rotate that stick to select colors; press again to close.|点击预览或按 L3／R3 开启色环，转动对应摇杆逐格选色，再按一次关闭。
紅色|Red|红色
橙色|Orange|橙色
黃色|Yellow|黄色
黃綠色|Lime|黄绿色
綠色|Green|绿色
薄荷綠|Mint|薄荷绿
青色|Cyan|青色
天藍色|Sky blue|天蓝色
藍色|Blue|蓝色
紫色|Purple|紫色
洋紅色|Magenta|洋红色
玫紅色|Rose|玫红色
點擊搖杆預覽或按下對應搖杆（L3／R3）開啟色環。|Tap a stick preview or press its stick (L3/R3) to open the color ring.|点击摇杆预览或按下对应摇杆（L3／R3）开启色环。
極端實驗性功能：可能完全無法工作，甚至可能導致 Android 分區無法啟動。|Extremely experimental: this may not work at all and may even prevent the Android partition from booting.|极端实验性功能：可能完全无法工作，甚至可能导致 Android 分区无法启动。
左搖杆燈|Left stick light|左摇杆灯
右搖杆燈|Right stick light|右摇杆灯
亮度與靈敏度|Brightness and sensitivity|亮度与灵敏度
亮度|Brightness|亮度
拖動兩個點：橫向調整最低／最高亮度，縱向調整靈敏度。|Drag the two points: X sets minimum/maximum brightness, Y sets sensitivity.|拖动两个点：横向调整最低／最高亮度，纵向调整灵敏度。
區域截圖|Region capture|区域截图
上屏截圖|Top screen capture|上屏截图
下屏截圖|Bottom screen capture|下屏截图
截圖模式|Capture mode|截图模式
點擊截圖，長按切換模式|Tap to capture, hold to change mode|点击截图，长按切换模式
找不到截圖屏幕|Capture screen is unavailable|找不到截图屏幕
截圖尺寸與屏幕配置不符|Capture size does not match screen layout|截图尺寸与屏幕配置不符
內錄來源|Playback source|内录来源
耳機|Headphones|耳机
揚聲器|Speakers|扬声器
跟隨桌面|Desktop default|跟随桌面
上屏|Top screen|上屏
下屏|Bottom screen|下屏
其他屏幕|Other screen|其他屏幕
新應用預設屏幕|New application screen|新应用默认屏幕
工作頁顯示應用所在屏幕；長按可移動並記住啟動屏幕。|Tasks show their screen. Hold a task to move it or remember its launch screen.|任务页显示应用所在屏幕；长按可移动并记住启动屏幕。
音量控制共用揚聲器，與上下屏無關。|Speaker volume is shared by both displays.|音量控制共用扬声器，与上下屏无关。
移到上屏|Move to top screen|移到上屏
移到下屏|Move to bottom screen|移到下屏
總是在上屏開啟|Always open on top screen|总是在上屏打开
總是在下屏開啟|Always open on bottom screen|总是在下屏打开
跟隨預設屏幕|Use default screen|跟随默认屏幕
燈光管理|Lighting|灯光管理
音頻律動|Audio reactive|音频律动
左燈 · 左聲道|Left light · left channel|左灯 · 左声道
右燈 · 右聲道|Right light · right channel|右灯 · 右声道
律動靈敏度|Audio sensitivity|律动灵敏度
顏色|Color|颜色
內錄播放音頻；左右聲道分別控制左右搖杆燈。靜音時燈光熄滅。|Playback audio drives the left and right stick lights separately. Silence turns the lights off.|内录播放音频；左右声道分别控制左右摇杆灯。静音时灯光熄灭。
音頻律動未啟用|Audio reactive lighting is off|音频律动未启用
無法讀取播放音頻|Cannot capture playback audio|无法读取播放音频
截圖失敗|Screenshot failed|截图失败
Android 使用硬體封裝加密；Linux 尚未支援解鎖。|Android hardware-wrapped encryption; Linux unlock is not yet supported.|Android 使用硬件封装加密；Linux 尚未支持解锁。
屏幕控制|Screen control|屏幕控制
雙屏亮度|Both displays|双屏亮度
音量|Volume|音量
靜音|Mute|静音
鎖定停用|Lock disabled|锁定停用
手動調節|Manual|手动调节
智慧調節|Adaptive|智能调节
手柄布局|Controller layout|手柄布局
布局不支援|Layout unavailable|布局不支持
旁路不支援|Bypass unavailable|旁路不支持
震動關閉|Rumble off|震动关闭
震動開啟|Rumble on|震动开启
燈光關閉|Lights off|灯光关闭
電量燈光|Battery lights|电量灯光
固定燈光|Static lights|固定灯光
浮層關閉|Overlay off|浮层关闭
浮層開啟|Overlay on|浮层开启
風扇管理|Fan|风扇管理
自訂|Custom|自定义
最熱感測器|Hottest sensor|最热传感器
平均感測器|Average sensors|平均传感器
複製為自訂|Copy to custom|复制为自定义
套用自訂曲線|Apply custom curve|应用自定义曲线
未套用的曲線|Unsaved curve|未应用的曲线
溫度須遞增，轉速不可遞減，最後一點須為 100%|Temperatures must rise, speeds must not fall, final speed must be 100%|温度须递增，转速不可递减，最后一点须为 100%
中控|Control|中控
模式|Modes|模式
工作|Tasks|任务
設定|Settings|设置
效能|Performance|性能
散熱|Cooling|散热
燈光|Lighting|灯光
螢幕|Displays|屏幕
按鍵|Buttons|按键
語言|Language|语言
跟隨系統|System language|跟随系统
溫度|Temperature|温度
風扇|Fan|风扇
電池|Battery|电池
電池溫度|Battery temperature|电池温度
顯示桌面|Show desktop|显示桌面
工作概覽|Overview|概览
中控台|Control panel|中控台
截圖|Screenshot|截图
移至另一螢幕|Move to other display|移至另一屏幕
停用|Disabled|停用
自訂指令|Custom command|自定义命令
自訂指令，例如 konsole|Custom command, e.g. konsole|自定义命令，例如 konsole
自動鎖定|Auto lock|自动锁定
安靜效能|Quiet|安静模式
標準效能|Balanced|标准模式
自訂效能|Custom|自定义模式
高效能|Performance|高性能
智慧模式|Smart mode|智能模式
清理記憶體|Clear cache|清理缓存
遊戲手柄|Gamepad|游戏手柄
滑鼠／鍵盤|Mouse / keyboard|鼠标／键盘
旁路供電|Bypass charging|旁路供电
未找到已確認的旁路供電控制介面|No confirmed bypass charging control|未找到已确认的旁路供电控制接口
震動|Vibration|振动
氛圍燈|Lighting|氛围灯
FPS 浮層|FPS overlay|FPS 浮层
不限幀|Unlimited|不限帧
安靜|Quiet|安静
標準|Balanced|标准
省電 CPU／GPU，較晚的風扇升速|Lower CPU/GPU power, quieter fan|省电 CPU／GPU，较晚的风扇升速
依負載調節 CPU／GPU，平衡風扇|Adaptive CPU/GPU, balanced fan|按负载调节 CPU／GPU，平衡风扇
最大 CPU／GPU 時脈，積極散熱|Maximum CPU/GPU clocks, active cooling|最大 CPU／GPU 频率，积极散热
啟動遊戲|Launch game|启动游戏
程式與參數|Program and arguments|程序与参数
上一頁|Previous|上一页
下一頁|Next|下一页
重新整理|Refresh|刷新
結束選取應用|End selected app|结束选中应用
結束應用|End app|结束应用
結束 |End |结束 
？未儲存的內容可能遺失。|? Unsaved work may be lost.|？未保存的内容可能丢失。
應用已退出或 PID 已被重用|App exited or PID was reused|应用已退出或 PID 已被复用
排程器|Scheduler|调度器
風扇策略|Fan profile|风扇策略
風扇感測|Fan sensor|风扇传感
低噪音|Quiet|低噪音
平衡|Balanced|平衡
強散熱|Active cooling|强散热
既有曲線|Existing curve|现有曲线
氛圍燈模式|Lighting mode|氛围灯模式
選擇氛圍燈顏色|Choose lighting color|选择氛围灯颜色
氛圍燈顏色|Lighting color|氛围灯颜色
氛圍燈亮度|Lighting brightness|氛围灯亮度
主螢幕亮度|Main display brightness|主屏幕亮度
副螢幕亮度|Secondary display brightness|副屏幕亮度
移動目前應用到另一螢幕|Move active app to other display|移动当前应用到另一屏幕
返回鍵|Back button|返回键
首頁鍵|Home button|主页键
指令| command|命令
分區|Partition|分区
按查詢讀取 Android 分區|Query Android partitions|查询 Android 分区
查詢|Query|查询
唯讀掛載|Mount read-only|只读挂载
卸載|Unmount|卸载
開啟 Android 目錄|Open Android folder|打开 Android 目录
上一組|Previous group|上一组
下一組|Next group|下一组
錯誤：|Error: |错误：
回覆格式錯誤：|Invalid response: |回复格式错误：
已套用設定|Settings applied|已应用设置
正在套用…|Applying…|正在应用…
已設定桌面自動鎖定|Desktop auto lock updated|已设置桌面自动锁定
服務已連線 · AYN 鍵切換中控|Connected · AYN toggles control panel|已连接 · AYN 键切换中控
服務已連線 · 手柄服務尚未就緒|Connected · Gamepad service unavailable|已连接 · 手柄服务尚未就绪
連線到硬體服務…|Connecting to hardware service…|连接硬件服务…
等待遊戲|Waiting for game|等待游戏
無法啟動：|Cannot start: |无法启动：
 結束碼 | exit code | 退出码 
未找到 Android 分區|No Android partitions found|未找到 Android 分区
可唯讀掛載|Read-only mounting available|可只读挂载
super 邏輯分區|super logical partition|super 逻辑分区
FPS 限制與浮層適用於 MangoHud 包裝的 OpenGL／Vulkan 遊戲。|FPS controls require MangoHud-wrapped OpenGL/Vulkan games.|FPS 限制与浮层适用于 MangoHud 包装的 OpenGL／Vulkan 游戏。
命令列：aynthor-control --run 遊戲程式 [參數]|Command: aynthor-control --run PROGRAM [ARGS]|命令行：aynthor-control --run 游戏程序 [参数]
執行中設定會由 MangoHud 自動重新載入。|MangoHud automatically reloads settings while running.|运行中设置由 MangoHud 自动重新加载。
'''
CATALOG = {}
for row in ROWS.strip('\n').splitlines():
    source,en,cn = row.split('|'); CATALOG[source] = {'en':en,'zh_CN':cn,'zh_TW':source}


def set_language(value):
    global LANGUAGE
    system = QLocale.system().name()
    LANGUAGE = value if value != 'system' else ('zh_TW' if system in ('zh_TW','zh_HK','zh_MO') else 'zh_CN' if system.startswith('zh') else 'en')
    if LANGUAGE not in ('en','zh_CN','zh_TW'): LANGUAGE = 'en'
    QLocale.setDefault(QLocale(LANGUAGE))


def tr(text):
    # One pass prevents replacement text from being translated a second time.
    import re
    pattern = '|'.join(re.escape(key) for key in sorted(CATALOG,key=len,reverse=True))
    return re.sub(pattern,lambda m:CATALOG[m[0]][LANGUAGE],text)


class Label(QtLabel):
    def __init__(self,text='',*args):
        super().__init__(*args); self.setText(text)

    def setText(self,text):
        self.source_text=text; super().setText(tr(text))

    def retranslate(self): super().setText(tr(self.source_text))


class Button(QtButton):
    def __init__(self,text='',*args):
        super().__init__(*args); self.setText(text)

    def setText(self,text):
        self.source_text=text; super().setText(tr(text))

    def retranslate(self): super().setText(tr(self.source_text))
