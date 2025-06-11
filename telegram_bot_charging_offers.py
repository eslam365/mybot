import json
import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.storage.memory import MemoryStorage
import datetime
from datetime import datetime

BOT_TOKEN = "8101619005:AAGS5w_eFZ4LB_vT41CSDARz6qSWNThLg7A"
ADMIN_IDS = [7515909688]  # ضع هنا معرفات المدراء (مالك البوت مثلاً)
VODAFONE_CASH_NUMBER = "01007360485"  # رقم محفظة فودافون كاش

DATA_FILE = "data.json"  # لتخزين الباقات، الطلبات، المستخدمين، الإحالات

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --------- أدوات المساعدة -----------

def load_data():
    if not os.path.exists(DATA_FILE):
        data = {
            "packages": [],
            "users": {},
            "orders": [],
        }
        save_data(data)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_package_name(package_id, data):
    return next((p['name'] for p in data['packages'] if str(p['id']) == str(package_id)), 'غير معروف')

# --------- حالات FSM -----------

class OrderStates(StatesGroup):
    waiting_payment_proof = State()
    waiting_activation_data = State()

class RechargeStates(StatesGroup):
    ask_amount = State()
    waiting_payment_details = State()
    waiting_screenshot = State()

class WithdrawStates(StatesGroup):
    waiting_withdraw_amount = State()
    waiting_payment_details = State()

class AdminWithdrawStates(StatesGroup):
    processing_withdraw = State()
    
# --------- أوامر المستخدم -----------

@dp.message(CommandStart())
async def cmd_start(message: Message):
    try:
        data = load_data()
        user_id = str(message.from_user.id)
        args = message.text.split()
        ref_id = args[1] if len(args) > 1 else ""
        
        # تسجيل مستخدم جديد مع التحقق من صحة الإحالة
        if user_id not in data["users"]:
            user_data = {
                "referral_from": None,
                "referrals_count": 0,
                "points": 0,
                "total_earned": 0  # إضافة حقل للأرباح الكلية من الإحالات
            }
            
            # التحقق من صحة رابط الإحالة وتسجيله
            if ref_id and ref_id.isdigit() and ref_id in data["users"] and ref_id != user_id:
                user_data["referral_from"] = ref_id
                data["users"][ref_id]["referrals_count"] += 1
            
            data["users"][user_id] = user_data
            save_data(data)

        # إذا كان المستخدم أدمن، عرض لوحة التحكم مباشرة
        if is_admin(message.from_user.id):
            await admin_panel(message)
            return
        
        # إعداد رسالة الترحيب للمستخدمين العاديين
        user_data = data["users"][user_id]
        bot_username = (await bot.get_me()).username
        welcome_text = (
            "مرحبًا بك في بوت الشحن!\n\n"
            f"👥 عدد الأشخاص الذين سجلوا عن طريقك: {user_data['referrals_count']}\n"
            "🔗 رابط الإحالة الخاص بك:\n"
            f"https://t.me/{bot_username}?start={user_id}"
        )
        
        # إعداد لوحة المفاتيح المعدلة
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💰 شحن الرصيد"), KeyboardButton(text="🧾 طلب جديد")],
                [KeyboardButton(text="🎁 نقاطي"), KeyboardButton(text="💳 سحب النقاط")],
                [KeyboardButton(text="ℹ️ الدعم")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(welcome_text, reply_markup=keyboard)
        
    except Exception as e:
        logging.error(f"Error in cmd_start: {e}")
        await message.answer("حدث خطأ غير متوقع. يرجى المحاولة لاحقاً.")

# --------- وظيفة شحن الرصيد المدمجة -----------

@dp.message(lambda msg: msg.text == "💰 شحن الرصيد")
async def recharge_balance(message: Message, state: FSMContext):
    await message.answer(
        "من فضلك أدخل قيمة الرصيد المطلوب (الحد الأدنى 50 جنيه):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RechargeStates.ask_amount)

@dp.message(RechargeStates.ask_amount)
async def ask_amount(message: Message, state: FSMContext):
    text = message.text
    try:
        amount = float(text)
        if amount < 50:
            await message.answer("❌ الحد الأدنى للشحن هو 50 جنيه. حاول مرة أخرى.")
            return
        
        total = round(amount * 1.25, 2)
        await state.update_data(amount=amount, total=total)
        
        await message.answer(
            f"✅ تم قبول الطلب.\n\n"
            f"💵 قيمة الشحن المطلوبة: {amount} جنيه\n"
            f"💰 المبلغ المطلوب دفعه: {total} جنيه\n"
            f"📱 ادفع الآن على محفظة فودافون كاش التالية:\n\n"
            f"🔢 {VODAFONE_CASH_NUMBER}\n\n"
            f"ثم أرسل لي البيانات التالية:\n"
            f"1- رقم الهاتف الذي تم الدفع منه\n"
            f"2- نفس قيمة الرصيد المطلوبة (للتحقق)\n"
            f"3- الرقم الذي تريد الشحن عليه\n"
            f"📸 وأخيرًا أرسل لقطة شاشة (إثبات الدفع)"
        )
        await state.set_state(RechargeStates.waiting_payment_details)
    except ValueError:
        await message.answer("❌ من فضلك أدخل رقم صحيح.")

@dp.message(RechargeStates.waiting_payment_details)
async def receive_text_details(message: Message, state: FSMContext):
    text = message.text
    parts = text.strip().split("\n")
    if len(parts) < 3:
        await message.answer("❗ أرسل البيانات كاملة:\n1- رقم الدفع منه\n2- قيمة الرصيد\n3- رقم الشحن")
        return
    
    phone_sent_from = parts[0].strip()
    phone_to_recharge = parts[1].strip()
    requested_amount = parts[2].strip()
    
    await state.update_data(
        phone_sent_from=phone_sent_from,
        phone_to_recharge=phone_to_recharge,
        requested_amount=requested_amount
    )
    
    await message.answer("📸 الآن أرسل لقطة شاشة لإثبات الدفع.")
    await state.set_state(RechargeStates.waiting_screenshot)

@dp.message(RechargeStates.waiting_screenshot)
async def receive_screenshot(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ من فضلك أرسل لقطة شاشة كصورة.")
        return
    
    data = load_data()
    recharge_data = await state.get_data()
    
    # حساب رقم الطلب
    last_order_id = max(
        max([o['order_id'] for o in data['orders']]) if data['orders'] else 0,
        max([r['order_id'] for r in data['recharge_orders']]) if data.get('recharge_orders') else 0
    )
    order_id = last_order_id + 1
    
    # حفظ طلب الشحن
    if "recharge_orders" not in data:
        data["recharge_orders"] = []
    
    new_recharge = {
        "order_id": order_id,
        "user_id": str(message.from_user.id),
        "username": message.from_user.username,
        "phone_sent_from": recharge_data.get("phone_sent_from"),
        "phone_to_recharge": recharge_data.get("phone_to_recharge"),
        "amount": recharge_data.get("amount"),
        "total": recharge_data.get("total"),
        "payment_proof_file_id": message.photo[-1].file_id,
        "status": "pending",
        "type": "recharge",
        "timestamp": datetime.now().isoformat()
    }
    data["recharge_orders"].append(new_recharge)
    
    # منح نقاط الإحالة إذا كان المستخدم جاء عن طريق إحالة
    user_id = str(message.from_user.id)
    if user_id in data["users"] and data["users"][user_id].get("referral_from"):
        referrer_id = data["users"][user_id]["referral_from"]
        if referrer_id in data["users"]:
            # حساب 4% من المبلغ (الحد الأدنى 1 نقطة)
            referral_bonus = max(1, int(float(recharge_data.get("amount", 0)) * 0.04))
            data["users"][referrer_id]["points"] = data["users"][referrer_id].get("points", 0) + referral_bonus
            data["users"][referrer_id]["total_earned"] = data["users"][referrer_id].get("total_earned", 0) + referral_bonus
            
            # إرسال إشعار للمحيل
            try:
                await bot.send_message(
                    chat_id=int(referrer_id),
                    text=f"🎉 لقد حصلت على {referral_bonus} نقطة (4%) من شحن رصيد قام به المستخدم الذي أحلتهم!"
                )
            except:
                pass
    
    save_data(data)

    
    # إرسال رسالة تأكيد للمستخدم
    await message.answer(
        "✅ تم استلام جميع البيانات.\n"
        f"📝 رقم الطلب: {order_id}\n"
        "⏳ الطلب قيد التنفيذ وسيتم تنفيذه خلال دقائق.\n"
        "شكراً لاستخدامك الخدمة!",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💰 شحن الرصيد"), KeyboardButton(text="🧾 طلب جديد")],
                [KeyboardButton(text="🎁 نقاطي"), KeyboardButton(text="💳 سحب النقاط")],
                [KeyboardButton(text="ℹ️ الدعم")]
            ],
            resize_keyboard=True
        )
    )
    
    # إرسال إشعار للمسؤولين
    admin_message = (
        f"🆕 طلب شحن جديد #{order_id}\n\n"
        f"👤 المستخدم: @{message.from_user.username}\n"
        f"📱 من رقم: {recharge_data.get('phone_sent_from')}\n"
        f"🔢 إلى رقم: {recharge_data.get('phone_to_recharge')}\n"
        f"💵 المبلغ: {recharge_data.get('amount')} جنيه\n"
        f"💰 الإجمالي: {recharge_data.get('total')} جنيه"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_message
            )
            await bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=f"إثبات الدفع للطلب #{order_id}"
            )
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id}: {e}")
    
    await state.clear()
    
# --------- باقي الكود الأصلي بدون تغيير -----------

@dp.message(lambda msg: msg.text == "🧾 الباقات")
async def order_button(message: Message):
    await start_order(message)  # يستخدم نفس دالة start_order الخاصة بـ /order
    
@dp.message(lambda msg: msg.text == "🧾 طلب جديد")
async def order_button(message: Message):
    await start_order(message)  # يستخدم نفس دالة start_order الخاصة بـ /order)


@dp.message(lambda msg: msg.text == "🎁 نقاطي")
async def points_button(message: Message):
    data = load_data()
    user_id = str(message.from_user.id)
    user = data["users"].get(user_id, {
        "referrals_count": 0,
        "points": 0,
        "total_earned": 0
    })
    
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    await message.answer(
        f"🎁 نقاطك:\n\n"
        f"⭐ النقاط الحالية: {user.get('points', 0)} (كل 100 نقطة = 1 جنيه)\n"
        f"💰 الأرباح الكلية من الإحالات: {user.get('total_earned', 0)} نقطة\n"
        f"👥 عدد الأحالات: {user.get('referrals_count', 0)}\n\n"
        f"🔗 رابط الإحالة الخاص بك:\n{referral_link}\n\n"
        f"معلومات المكافآت:\n"
        f"- عند شراء أحالتك لباقة: 10 نقاط\n"
        f"- عند شحن أحالتك لرصيد: 4% من المبلغ\n\n"
        f"💳 يمكنك سحب النقاط عند الوصول إلى 50 نقطة فأكثر"
    )

@dp.message(lambda msg: msg.text == "ℹ️ الدعم")
async def support_button(message: Message):
    await message.answer("للتواصل مع الدعم، يرجى مراسلتنا عبر:\n@eslam_lp")


@dp.message(Command(commands=["packages"]))
async def show_packages(message: Message):
    data = load_data()
    if not data["packages"]:
        await message.answer("لا توجد باقات حالياً.")
        return
    
    text = "📦 الباقات المتاحة:\n\n"
    for p in data["packages"]:
        text += (
            f"🔹 *{p['name']}*\n"
            f"💰 السعر: {p['price']} جنيه\n"
            f"📝 الوصف: {p.get('description', 'لا يوجد وصف')}\n\n"
        )
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command(commands=["order"]))
@dp.message(lambda msg: msg.text == "🧾 طلب جديد")
async def start_order(message: Message):
    data = load_data()
    if not data["packages"]:
        await message.answer("لا توجد باقات حالياً.")
        return
    
    text = "📦 الباقات المتاحة:\n\n"
    for p in data["packages"]:
        text += (
            f"🔹 *{p['name']}*\n"
            f"💰 السعر: {p['price']} جنيه\n"
            f"📝 الوصف: {p.get('description', 'لا يوجد وصف')}\n\n"
        )
    
    kb = InlineKeyboardBuilder()
    for p in data["packages"]:
        kb.button(text=f"{p['name']} — {p['price']} جنيه", callback_data=f"order_{p['id']}")
    kb.adjust(1)
    
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(lambda c: c.data and c.data.startswith("order_"))
async def process_order_callback(callback: CallbackQuery, state: FSMContext):
    data = load_data()
    package_id = callback.data.split("_")[1]
    pkg = next((p for p in data["packages"] if str(p["id"]) == package_id), None)
    if not pkg:
        await callback.message.answer("الباقة غير موجودة.")
        return

    await callback.message.answer(
        f"لقد اخترت باقة:\n\n"
        f"🔹 *{pkg['name']}*\n"
        f"💰 السعر: {pkg['price']} جنيه\n"
        f"📝 الوصف: {pkg.get('description', 'لا يوجد وصف')}\n\n"
        "برجاء الدفع علي محفظه فودافون كاش التاليه:\n"
        "01007360485\n"
        "ثم ارسل لقطه شاشه باثبات الدفع",
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.waiting_payment_proof)
    await callback.answer()

@dp.message(OrderStates.waiting_payment_proof)
async def payment_proof_received(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("يرجى إرسال صورة إثبات الدفع (لقطة شاشة).")
        return

    data = load_data()
    photo = message.photo[-1]
    file_id = photo.file_id

    data_state = await state.get_data()
    package_id = data_state.get("package_id")
    user_id = str(message.from_user.id)

    await state.update_data(payment_proof_file_id=file_id)
    await message.answer("تم استلام إثبات الدفع. الآن أرسل بيانات التفعيل (مثل رقم الهاتف وباسورد انا فودافون).")
    await state.set_state(OrderStates.waiting_activation_data)

@dp.message(OrderStates.waiting_activation_data)
async def activation_data_received(message: Message, state: FSMContext):
    data = load_data()
    activation_data = message.text
    data_state = await state.get_data()
    package_id = data_state.get("package_id")
    payment_proof_file_id = data_state.get("payment_proof_file_id")
    user_id = str(message.from_user.id)

    order_id = len(data["orders"]) + 1
    new_order = {
        "order_id": order_id,
        "user_id": user_id,
        "package_id": package_id,
        "payment_proof_file_id": payment_proof_file_id,
        "activation_data": activation_data,
        "status": "pending"
    }
    data["orders"].append(new_order)
    
    # منح نقاط الإحالة إذا كان المستخدم جاء عن طريق إحالة
    if user_id in data["users"] and data["users"][user_id].get("referral_from"):
        referrer_id = data["users"][user_id]["referral_from"]
        if referrer_id in data["users"]:
            # إضافة 10 نقاط للمحيل
            data["users"][referrer_id]["points"] = data["users"][referrer_id].get("points", 0) + 10
            data["users"][referrer_id]["total_earned"] = data["users"][referrer_id].get("total_earned", 0) + 10
            
            # إرسال إشعار للمحيل
            try:
                await bot.send_message(
                    chat_id=int(referrer_id),
                    text="🎉 لقد حصلت على 10 نقاط من شراء باقة قام به المستخدم الذي أحلتهم!"
                )
            except:
                pass
    
    save_data(data)


    await message.answer("تم تسجيل طلبك، وسيتم مراجعته وتنفيذه قريبًا. شكرًا لك!")

    for admin_id in ADMIN_IDS:
        text = (
            f"طلب جديد من المستخدم [{user_id}](tg://user?id={user_id}):\n"
            f"الباقة: {get_package_name(package_id, data)}\n"
            f"بيانات التفعيل: {activation_data}\n"
            f"الحالة: قيد الانتظار\n"
            f"إثبات الدفع:"
        )
        await bot.send_message(admin_id, text, parse_mode="Markdown")
        await bot.send_photo(admin_id, payment_proof_file_id)

    await state.clear()

@dp.message(lambda msg: msg.text == "💳 سحب النقاط")
async def start_withdraw(message: Message, state: FSMContext):
    data = load_data()
    user_id = str(message.from_user.id)
    user_points = data["users"].get(user_id, {}).get("points", 0)
    
    if user_points < 50:
        await message.answer("❌ الحد الأدنى لسحب النقاط هو 50 نقطة.")
        return
    
    await message.answer(
        f"💳 لديك {user_points} نقطة.\n"
        "أدخل عدد النقاط التي تريد سحبها (الحد الأدنى 50 نقطة):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(WithdrawStates.waiting_withdraw_amount)

@dp.message(WithdrawStates.waiting_withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    try:
        points = int(message.text)
        if points < 50:
            await message.answer("❌ الحد الأدنى لسحب النقاط هو 50 نقطة.")
            return
            
        data = load_data()
        user_id = str(message.from_user.id)
        user_points = data["users"].get(user_id, {}).get("points", 0)
        
        if points > user_points:
            await message.answer(f"❌ لا تمتلك نقاط كافية. لديك فقط {user_points} نقطة.")
            return
            
        await state.update_data(points=points)
        await message.answer(
            "📋 أرسل بيانات التحويل البنكي أو رقم محفظتك:\n"
            "1. اسم البنك أو المحفظة\n"
            "2. رقم الحساب أو المحفظة\n"
            "3. الاسم كما هو مسجل في الحساب"
        )
        await state.set_state(WithdrawStates.waiting_payment_details)
        
    except ValueError:
        await message.answer("❌ من فضلك أدخل رقم صحيح.")

@dp.message(WithdrawStates.waiting_payment_details)
async def process_payment_details(message: Message, state: FSMContext):
    payment_details = message.text
    withdraw_data = await state.get_data()
    points = withdraw_data.get("points")
    
    data = load_data()
    user_id = str(message.from_user.id)
    
    # إنشاء طلب سحب جديد
    if "withdraw_requests" not in data:
        data["withdraw_requests"] = []
    
    withdraw_id = len(data["withdraw_requests"]) + 1
    new_withdraw = {
        "id": withdraw_id,
        "user_id": user_id,
        "username": message.from_user.username,
        "points": points,
        "payment_details": payment_details,
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }
    data["withdraw_requests"].append(new_withdraw)
    
    # خصم النقاط من رصيد المستخدم
    data["users"][user_id]["points"] -= points
    save_data(data)
    
    # إرسال إشعار للمشرفين
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆘 طلب سحب جديد #{withdraw_id}\n\n"
                f"👤 المستخدم: @{message.from_user.username}\n"
                f"💎 النقاط: {points}\n"
                f"📋 بيانات التحويل:\n{payment_details}"
            )
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id}: {e}")
    
    await message.answer(
        f"✅ تم تقديم طلب السحب بنجاح!\n\n"
        f"رقم الطلب: #{withdraw_id}\n"
        f"النقاط المسحوبة: {points}\n\n"
        "سيتم مراجعة طلبك وإعلامك بالقرار.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💰 شحن الرصيد"), KeyboardButton(text="🧾 طلب جديد")],
                [KeyboardButton(text="🎁 نقاطي"), KeyboardButton(text="💳 سحب النقاط")],
                [KeyboardButton(text="ℹ️ الدعم")]
            ],
            resize_keyboard=True
        )
    )
    await state.clear()
    
# --------- أوامر المدير -----------

# إضافة إلى الكود الرئيسي - لوحة تحكم المدير متكاملة

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

ADMIN_IDS = [7515909688]  # معرفات المدراء

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ----- حالات خاصة بالإدمن -----
class AdminStates(StatesGroup):
    adding_package = State()

# ----- لوحة التحكم الرئيسية -----
@dp.message(Command(commands=["admin"]))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول للوحة التحكم.")
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 عرض الباقات")],
            [KeyboardButton(text="➕ إضافة باقة")],
            [KeyboardButton(text="📬 عرض الطلبات المعلقة")],
            [KeyboardButton(text="💎 طلبات السحب")],
        ],
        resize_keyboard=True,
        input_field_placeholder="اختر خيارًا من لوحة التحكم"
    )

    await message.answer("🔧 *لوحة تحكم المدير:*", reply_markup=kb, parse_mode="Markdown")

@dp.message(lambda message: message.text == "📦 عرض الباقات")
async def admin_view_packages(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    data = load_data()
    
    if not data["packages"]:
        await message.answer("📦 لا توجد باقات حالياً.")
        return
    
    # إنشاء لوحة المفاتيح للعودة
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 العودة للوحة التحكم")]],
        resize_keyboard=True
    )
    
    # بناء نص عرض الباقات
    text = "📦 *قائمة الباقات المتاحة:*\n\n"
    for p in data["packages"]:
        text += f"▫️ *ID:* `{p['id']}`\n"
        text += f"▫️ *الاسم:* {p['name']}\n"
        text += f"▫️ *السعر:* {p['price']} جنيه\n"
        text += f"▫️ *الوصف:* {p.get('description', 'لا يوجد وصف')}\n"
        text += "――――――――――――――――――\n\n"
    
    await message.answer(
        text,
        reply_markup=back_kb,
        parse_mode="Markdown"
    )

# معالج العودة للوحة التحكم
@dp.message(lambda message: message.text == "🔙 العودة للوحة التحكم")
async def back_to_admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 عرض الباقات")],
            [KeyboardButton(text="➕ إضافة باقة")],
            [KeyboardButton(text="📬 عرض الطلبات المعلقة")],
            [KeyboardButton(text="💎 طلبات السحب")],
        ],
        resize_keyboard=True
    )
    
    await message.answer("🔧 *لوحة تحكم المدير:*", reply_markup=kb, parse_mode="Markdown")

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    adding_package = State()
    completing_order = State()

# ----- إضافة باقة -----
@dp.message(lambda message: message.text == "➕ إضافة باقة")
async def start_add_package(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 إلغاء الإضافة")]],
        resize_keyboard=True
    )
    
    await state.set_state(AdminStates.adding_package)
    await message.answer(
        "✏️ أرسل بيانات الباقة بهذا الشكل:\n`اسم الباقة;السعر;الوصف`\nمثال:\n`باقة الذهب;150;هذه باقة مميزة لشحن الرصيد`",
        reply_markup=back_kb,
        parse_mode="Markdown"
    )

@dp.message(AdminStates.adding_package)
async def process_add_package(message: Message, state: FSMContext):
    if message.text == "🔙 إلغاء الإضافة":
        await state.clear()
        await back_to_admin_panel(message)
        return
    
    try:
        # تقسيم النص إلى أجزاء (الاسم، السعر، الوصف)
        parts = message.text.split(";", 2)
        if len(parts) < 3:
            raise ValueError("يجب إدخال جميع الحقول")
            
        name = parts[0].strip()
        price = float(parts[1].strip())
        description = parts[2].strip()
    except:
        await message.answer("❌ الصيغة غير صحيحة. أرسلها بهذا الشكل:\n`اسم الباقة;السعر;الوصف`\nمثال:\n`باقة الذهب;150;هذه باقة مميزة لشحن الرصيد`", parse_mode="Markdown")
        return

    data = load_data()
    new_id = max(p["id"] for p in data["packages"]) + 1 if data["packages"] else 1
    
    data["packages"].append({
        "id": new_id,
        "name": name,
        "price": price,
        "description": description
    })
    
    save_data(data)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 عرض الباقات")],
            [KeyboardButton(text="➕ إضافة باقة")],
            [KeyboardButton(text="📬 عرض الطلبات المعلقة")],
            [KeyboardButton(text="💎 طلبات السحب")],
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ تم إضافة الباقة بنجاح:\n\n"
        f"▫️ *الاسم:* {name}\n"
        f"▫️ *السعر:* {price} جنيه\n"
        f"▫️ *الوصف:* {description}\n"
        f"▫️ *رقم الباقة:* {new_id}",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.clear()

# ----- عرض الطلبات المعلقة -----
# ----- عرض الطلبات المعلقة -----
@dp.message(lambda message: message.text == "📬 عرض الطلبات المعلقة")
async def admin_list_orders_menu(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    menu_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 طلبات الباقات")],
            [KeyboardButton(text="💰 طلبات الشحن")],
            [KeyboardButton(text="🔙 العودة للوحة التحكم")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "اختر نوع الطلبات التي تريد عرضها:",
        reply_markup=menu_kb
    )

@dp.message(lambda message: message.text == "📦 طلبات الباقات")
async def admin_list_package_orders(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    data = load_data()
    if not data or "orders" not in data:
        await message.answer("📭 لا توجد طلبات باقات معلقة حالياً.")
        return
    
    pending_orders = [o for o in data["orders"] if o.get("status") == "pending"]
    
    if not pending_orders:
        await message.answer("📭 لا توجد طلبات باقات معلقة حالياً.")
        return
    
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 العودة للوحة التحكم")]],
        resize_keyboard=True
    )
    
    await message.answer(
        f"📦 طلبات الباقات المعلقة ({len(pending_orders)})",
        reply_markup=back_kb
    )
    
    for order in pending_orders:
        try:
            pkg_name = get_package_name(order.get('package_id'), data)
            user = await bot.get_chat(order.get("user_id"))
            
            text = (
                f"📦 طلب باقة\n"
                f"▫️ رقم الطلب: {order.get('order_id')}\n"
                f"▫️ المستخدم: {user.first_name}\n"
                f"▫️ الباقة: {pkg_name}\n"
                f"▫️ بيانات التفعيل:\n{order.get('activation_data')}\n"
                f"――――――――――――――――――"
            )
            
            action_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=f"✅ تنفيذ {order.get('order_id')}")],
                    [KeyboardButton(text=f"❌ رفض {order.get('order_id')}")],
                    [KeyboardButton(text="🔙 العودة للوحة التحكم")]
                ],
                resize_keyboard=True
            )
            
            if "payment_proof_file_id" in order:
                await bot.send_photo(
                    chat_id=message.chat.id,
                    photo=order["payment_proof_file_id"],
                    caption=text
                )
                await message.answer("اختر إجراء للطلب:", reply_markup=action_kb)
            else:
                await message.answer(text, reply_markup=action_kb)
                
        except Exception as e:
            print(f"Error displaying order {order.get('order_id')}: {e}")
            await message.answer(f"⚠️ حدث خطأ في عرض الطلب {order.get('order_id')}")

@dp.message(lambda message: message.text.startswith("✅ تنفيذ "))
async def approve_order(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    try:
        order_id = message.text.replace("✅ تنفيذ ", "").strip()
        data = load_data()
        
        # البحث في طلبات الباقات
        for order in data.get("orders", []):
            if str(order.get("order_id")) == str(order_id) and order.get("status") == "pending":
                order["status"] = "completed"
                save_data(data)
                
                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=f"✅ تم تنفيذ طلبك #{order_id} بنجاح!\nشكراً لاستخدامك خدماتنا."
                    )
                except Exception as e:
                    print(f"Failed to notify user: {e}")
                
                await message.answer(f"✅ تم تنفيذ الطلب #{order_id} بنجاح.")
                return
        
        # البحث في طلبات الشحن إذا لم يوجد في الباقات
        for recharge in data.get("recharge_orders", []):
            if str(recharge.get("order_id")) == str(order_id) and recharge.get("status") == "pending":
                recharge["status"] = "completed"
                save_data(data)
                
                try:
                    await bot.send_message(
                        chat_id=recharge["user_id"],
                        text=f"✅ تم تنفيذ طلب الشحن #{order_id} بنجاح!\nتم شحن الرصيد بنجاح."
                    )
                except Exception as e:
                    print(f"Failed to notify user: {e}")
                
                await message.answer(f"✅ تم تنفيذ طلب الشحن #{order_id} بنجاح.")
                return
        
        await message.answer(f"❌ لم يتم العثور على الطلب #{order_id} أو تم معالجته مسبقاً.")
        
    except Exception as e:
        print(f"Error approving order {order_id}: {e}")
        await message.answer(f"⚠️ حدث خطأ أثناء معالجة الطلب: {e}")

@dp.message(lambda message: message.text.startswith("❌ رفض "))
async def reject_order(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    try:
        order_id = message.text.replace("❌ رفض ", "").strip()
        data = load_data()
        
        # البحث في طلبات الباقات
        for order in data.get("orders", []):
            if str(order.get("order_id")) == str(order_id) and order.get("status") == "pending":
                order["status"] = "rejected"
                save_data(data)
                
                try:
                    await bot.send_message(
                        chat_id=order["user_id"],
                        text=f"❌ تم رفض طلبك #{order_id}.\nللمزيد من المعلومات، يرجى التواصل مع الدعم."
                    )
                except Exception as e:
                    print(f"Failed to notify user: {e}")
                
                await message.answer(f"❌ تم رفض الطلب #{order_id}.")
                return
        
        # البحث في طلبات الشحن إذا لم يوجد في الباقات
        for recharge in data.get("recharge_orders", []):
            if str(recharge.get("order_id")) == str(order_id) and recharge.get("status") == "pending":
                recharge["status"] = "rejected"
                save_data(data)
                
                try:
                    await bot.send_message(
                        chat_id=recharge["user_id"],
                        text=f"❌ تم رفض طلب الشحن #{order_id}.\nللمزيد من المعلومات، يرجى التواصل مع الدعم."
                    )
                except Exception as e:
                    print(f"Failed to notify user: {e}")
                
                await message.answer(f"❌ تم رفض طلب الشحن #{order_id}.")
                return
        
        await message.answer(f"❌ لم يتم العثور على الطلب #{order_id} أو تم معالجته مسبقاً.")
        
    except Exception as e:
        print(f"Error rejecting order {order_id}: {e}")
        await message.answer(f"⚠️ حدث خطأ أثناء معالجة الطلب: {e}")

@dp.message(lambda message: message.text == "💰 طلبات الشحن")
async def admin_list_recharge_orders(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    data = load_data()
    if not data or "recharge_orders" not in data:
        await message.answer("📭 لا توجد طلبات شحن معلقة حالياً.")
        return
    
    pending_recharges = [r for r in data["recharge_orders"] if r.get("status") == "pending"]
    
    if not pending_recharges:
        await message.answer("📭 لا توجد طلبات شحن معلقة حالياً.")
        return
    
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 العودة للوحة التحكم")]],
        resize_keyboard=True
    )
    
    await message.answer(
        f"💰 طلبات الشحن المعلقة ({len(pending_recharges)})",
        reply_markup=back_kb
    )
    
    for recharge in pending_recharges:
        try:
            user = await bot.get_chat(recharge.get("user_id"))
            
            text = (
                f"💰 طلب شحن رصيد\n"
                f"▫️ رقم الطلب: {recharge.get('order_id')}\n"
                f"▫️ المستخدم: {user.first_name}\n"
                f"▫️ رقم الدفع: {recharge.get('phone_sent_from', 'غير معروف')}\n"
                f"▫️ رقم الشحن: {recharge.get('phone_to_recharge', 'غير معروف')}\n"
                f"▫️ المبلغ: {recharge.get('amount', 'غير معروف')} جنيه\n"
                f"――――――――――――――――――"
            )
            
            action_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=f"✅ تنفيذ {recharge.get('order_id')}")],
                    [KeyboardButton(text=f"❌ رفض {recharge.get('order_id')}")],
                    [KeyboardButton(text="🔙 العودة للوحة التحكم")]
                ],
                resize_keyboard=True
            )
            
            if "payment_proof_file_id" in recharge:
                await bot.send_photo(
                    chat_id=message.chat.id,
                    photo=recharge["payment_proof_file_id"],
                    caption=text
                )
                await message.answer("اختر إجراء للطلب:", reply_markup=action_kb)
            else:
                await message.answer(text, reply_markup=action_kb)
                
        except Exception as e:
            print(f"Error displaying recharge {recharge.get('order_id')}: {e}")
            await message.answer(f"⚠️ حدث خطأ في عرض طلب الشحن {recharge.get('order_id')}")
        
# ----- تنفيذ طلب يدويًا -----
@dp.message(lambda message: message.text == "✅ تنفيذ طلب")
async def start_complete_order(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    await state.set_state(AdminStates.completing_order)
    
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 إلغاء التنفيذ")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "✏️ أرسل رقم الطلب الذي تريد تنفيذه:",
        reply_markup=back_kb
    )

@dp.message(AdminStates.completing_order)
async def complete_order_manually(message: Message, state: FSMContext):
    if message.text == "🔙 إلغاء التنفيذ":
        await state.clear()
        await back_to_admin_panel(message)
        return
    
    try:
        order_id = int(message.text)
        data = load_data()
        order = next((o for o in data["orders"] if o["order_id"] == order_id), None)
        
        if not order:
            await message.answer("❌ لا يوجد طلب بهذا الرقم.")
            return
        
        if order["status"] != "pending":
            await message.answer(f"⚠️ هذا الطلب تم {order['status']} مسبقاً.")
            return
        
        order["status"] = "completed"
        save_data(data)
        
        user_id = int(order["user_id"])
        pkg_name = get_package_name(order['package_id'], data)
        
        await bot.send_message(
            user_id,
            f"🎉 تم تنفيذ طلبك بنجاح!\n\n"
            f"▫️ *رقم الطلب:* {order_id}\n"
            f"▫️ *الباقة:* {pkg_name}\n\n"
            f"شكراً لثقتك بنا!",
            parse_mode="Markdown"
        )
        
        await message.answer(
            f"✅ تم تنفيذ الطلب رقم {order_id} بنجاح.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📬 عرض الطلبات المعلقة")]],
                resize_keyboard=True
            )
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم الطلب صحيح (أرقام فقط).")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {e}") 

@dp.message(lambda message: message.text == "💎 طلبات السحب")
async def admin_list_withdrawals(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ ليس لديك صلاحية الوصول لهذه الصلاحية.")
        return
    
    data = load_data()
    pending_withdrawals = [w for w in data.get("withdraw_requests", []) if w.get("status") == "pending"]
    
    if not pending_withdrawals:
        await message.answer("📭 لا توجد طلبات سحب معلقة حالياً.")
        return
    
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 العودة للوحة التحكم")]],
        resize_keyboard=True
    )
    
    await message.answer(
        f"💎 طلبات السحب المعلقة ({len(pending_withdrawals)})",
        reply_markup=back_kb
    )
    
    for withdraw in pending_withdrawals:
        try:
            user = await bot.get_chat(withdraw.get("user_id"))
            
            text = (
                f"💎 طلب سحب #{withdraw.get('id')}\n"
                f"👤 المستخدم: {user.first_name} (@{user.username})\n"
                f"💎 النقاط: {withdraw.get('points')}\n"
                f"📋 بيانات التحويل:\n{withdraw.get('payment_details')}\n"
                f"⏰ التاريخ: {withdraw.get('timestamp')}\n"
                f"――――――――――――――――――"
            )
            
            action_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=f"✅ قبول السحب {withdraw.get('id')}")],
                    [KeyboardButton(text="🔙 العودة للوحة التحكم")]
                ],
                resize_keyboard=True
            )
            
            await message.answer(text, reply_markup=action_kb)
                
        except Exception as e:
            print(f"Error displaying withdrawal {withdraw.get('id')}: {e}")
            await message.answer(f"⚠️ حدث خطأ في عرض طلب السحب {withdraw.get('id')}")

@dp.message(lambda message: message.text.startswith("✅ قبول السحب "))
async def approve_withdrawal(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    try:
        withdraw_id = int(message.text.replace("✅ قبول السحب ", ""))
        data = load_data()
        
        for withdraw in data.get("withdraw_requests", []):
            if withdraw.get("id") == withdraw_id and withdraw.get("status") == "pending":
                withdraw["status"] = "completed"
                save_data(data)
                
                try:
                    await bot.send_message(
                        withdraw["user_id"],
                        f"🎉 تمت الموافقة على طلب السحب #{withdraw_id}!\n"
                        f"تم تحويل النقاط بنجاح إلى حسابك."
                    )
                except Exception as e:
                    print(f"Failed to notify user: {e}")
                
                await message.answer(f"✅ تمت الموافقة على طلب السحب #{withdraw_id}.")
                return
        
        await message.answer(f"❌ لم يتم العثور على طلب السحب #{withdraw_id} أو تم معالجته مسبقاً.")
        
    except Exception as e:
        print(f"Error approving withdrawal {withdraw_id}: {e}")
        await message.answer(f"⚠️ حدث خطأ أثناء معالجة طلب السحب: {e}")

        
# --------- تشغيل البوت -----------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())