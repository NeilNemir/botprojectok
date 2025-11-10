from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from generators import (
    get_group_id, set_group_id, get_roles, set_all_me, set_initiator,
    list_methods, get_method_by_id,
    create_payment, set_group_message, get_payment, approve_payment, reject_payment,
    list_pending, list_user_payments, get_payment_compact, export_payments_csv,
    set_approver, set_viewer,
)
from generators import delete_method, list_custom_methods, ALLOWED_METHODS, init_db, DB_PATH

router = Router()

CURRENCY = "THB"

# ========= Категории расходов =========
CATEGORIES = [
    ("🛵 Rent & Utilities", "rent"),
    ("🥳 Salaries & Employee Payments", "salaries"),
    ("🫰🏼 Transport & Logistics", "transport"),
    ("👀 Marketing & Advertising", "marketing"),
    ("👨🏽‍💻 IT & Services", "it"),
    ("💸 Operating Expenses (Other)", "operating"),
]

def get_category_label_by_code(code: str) -> str:
    for label, c in CATEGORIES:
        if c == code:
            return label
    return "📦 Operating Expenses (Other)"

# ========= Клавиатуры =========

def kb_nav(back: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if back:
        rows.append([InlineKeyboardButton(text="👈🏼 Back", callback_data="nav:back")])
    rows.append([InlineKeyboardButton(text="🫣 Cancel", callback_data="nav:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"cat:{code}")] for label, code in CATEGORIES]
    rows.append([
        InlineKeyboardButton(text="👈🏼 Back", callback_data="nav:back"),
        InlineKeyboardButton(text="🫣 Cancel", callback_data="nav:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def methods_kb() -> InlineKeyboardMarkup:
    # Показываем только методы из БД (поддерживаются миграциями/whitelist'ом)
    rows: list[list[InlineKeyboardButton]] = []
    for _mid, name in list_methods():
        rows.append([InlineKeyboardButton(text=name, callback_data=f"methodname:{name}")])
    # Без "+ Add method", Back, Cancel
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_group_approve(pid: int) -> InlineKeyboardMarkup:
    # Единая кнопка Approve + Reject
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🔋 Approve", callback_data=f"approve:{pid}"),
            InlineKeyboardButton(text="🪫 Reject", callback_data=f"reject:{pid}"),
        ]]
    )

# ========= Утилиты =========

def fmt_amount(val: float) -> str:
    if float(val).is_integer():
        return f"{int(val):,}".replace(",", ".")
    s = f"{val:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return s


def render_card(p: dict) -> str:
    category_text = p.get("category") or "📦 Operating Expenses (Other)"
    lines = [
        f"#PAY-{p['id']}",
        f"• {fmt_amount(p['amount'])} {p.get('currency', CURRENCY)}",
        f"• {p['method']}",
        f"• {category_text}",
        "",
        f"• Description: {p['description']}",
        "",
        f"Status: {p['status']}",
        f"Initiator: {p['initiator_id']}",
        "",
        f"Created: {p['created_at']}",
    ]
    if p.get("approved_by"):
        lines.append(f"✅ Approved by: {p['approved_by']} at {p.get('approved_at','')}")
    if p.get("rejected_by"):
        lines.append(f"Rejected by: {p['rejected_by']} at {p.get('rejected_at','')}")
    return "\n".join(lines)


def render_line(row) -> str:
    cat = row.get("category") or "📦 Operating Expenses (Other)"
    return (
        f"#PAY-{row['id']} — {fmt_amount(row['amount'])} {row['currency']} — "
        f"{row['method']} — {cat} — {row['status']} — {row['created_at']}"
    )

# ========= Базовые команды =========

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "✅ Bot online.\n"
        "Commands: /ping, /newpay, /methods, /pending, /my, /pay <id>, /export_csv, /whoami, /roles, /set_all_me, /set_initiator <id>, /set_approver <id>, /set_viewer <id>, /setup_here (in group), /ver"
    )


@router.message(Command("ver"))
async def cmd_ver(message: Message) -> None:
    await message.answer("build: sqlite-payments-lists-004")


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong")


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    await message.answer(f"Your id: {message.from_user.id}")


@router.message(Command("roles"))
async def cmd_roles(message: Message) -> None:
    roles = get_roles()
    gid = get_group_id()
    await message.answer(
        "Roles:\n"
        f"- initiator_id: {roles['initiator_id']}\n"
        f"- approver_id: {roles['approver_id']}\n"
        f"- viewer_id: {roles['viewer_id']}\n"
        f"- group_id: {gid}"
    )


@router.message(Command("set_all_me"))
async def cmd_set_all_me_cmd(message: Message) -> None:
    set_all_me(message.from_user.id)
    await message.answer("✅ Saved to DB: you are initiator + approver + viewer. Use /roles to check.")


@router.message(Command("set_initiator"))
async def cmd_set_initiator_cmd(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /set_initiator <id>")
        return

    new_init = int(parts[1])
    current_init = get_roles()["initiator_id"]

    if current_init is not None and message.from_user and message.from_user.id != current_init:
        await message.answer("Only current initiator can change initiator ID.")
        return

    set_initiator(new_init)
    await message.answer(f"✅ Initiator set to {new_init}")


@router.message(Command("set_approver"))
async def cmd_set_approver_cmd(message: Message) -> None:
    roles = get_roles()
    if not roles["initiator_id"] or (message.from_user and message.from_user.id != roles["initiator_id"]):
        await message.answer("Only initiator can change approver. Ask admin to change roles.")
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /set_approver <approver_id>")
        return

    approver_id = int(parts[1])
    set_approver(approver_id)
    await message.answer(f"✅ Approver set to {approver_id}")


@router.message(Command("set_viewer"))
async def cmd_set_viewer_cmd(message: Message) -> None:
    roles = get_roles()
    if not roles["initiator_id"] or (message.from_user and message.from_user.id != roles["initiator_id"]):
        await message.answer("Only initiator can change viewer. Ask admin to change roles.")
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /set_viewer <viewer_id>")
        return

    viewer_id = int(parts[1])
    set_viewer(viewer_id)
    await message.answer(f"✅ Viewer set to {viewer_id}")


async def _bind_group(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Run this command inside the target group.")
        return
    set_group_id(message.chat.id)
    await message.answer(f"✅ Group bound: chat_id = {message.chat.id}")


@router.message(Command("setup_here"))
async def cmd_setup_here(message: Message) -> None:
    await _bind_group(message)


@router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().startswith("/setup_here")))
async def cmd_setup_here_fallback(message: Message) -> None:
    await _bind_group(message)


@router.message(Command("methods"))
async def cmd_methods(message: Message) -> None:
    rows = list_methods()
    if not rows:
        await message.answer("No methods.")
        return
    text = "Methods:\n" + "\n".join([f"- {name} (id {mid})" for mid, name in rows])
    await message.answer(text)


# ========= Reset bot DB (initiator only) =========
@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None or (message.from_user and message.from_user.id != roles["initiator_id"]):
        await message.answer("Only initiator can reset the bot.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Confirm full reset", callback_data="reset_confirm")],
        [InlineKeyboardButton(text="✖️ Cancel", callback_data="reset_cancel")],
    ])
    await message.answer(
        "This will delete all data (roles, payments, bindings). Methods whitelist will be restored.\n"
        "After reset, run /setup_here in the target group and set roles again.\n\nProceed?",
        reply_markup=kb,
    )


@router.callback_query(F.data == "reset_cancel")
async def cb_reset_cancel(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text("Reset cancelled.")
    except Exception:
        await call.message.answer("Reset cancelled.")
    await call.answer()


@router.callback_query(F.data == "reset_confirm")
async def cb_reset_confirm(call: CallbackQuery, state: FSMContext) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None or call.from_user.id != roles["initiator_id"]:
        await call.answer("Only initiator can reset the bot", show_alert=True)
        return
    # Try to remove DB and reinit
    import os
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except Exception as e:
        await call.answer(f"Failed to remove DB: {e}", show_alert=True)
        return
    # Recreate schema and whitelist
    try:
        init_db()
        # Set current user as initiator to keep control after reset
        set_initiator(call.from_user.id)
        await state.clear()
    except Exception as e:
        await call.answer(f"Failed to init DB: {e}", show_alert=True)
        return

    msg = (
        "✅ Bot storage reset.\n"
        "• Methods whitelist restored (Bank of Company, USDT, Cash).\n"
        "• Initiator set to you.\n"
        "• Group binding cleared — run /setup_here in the target group."
    )
    try:
        await call.message.edit_text(msg)
    except Exception:
        await call.message.answer(msg)
    await call.answer("Reset done")


# ========= Удаление методов (только инициатор) =========
@router.message(Command("delete_method"))
@router.message(Command("del_method"))
async def cmd_delete_method(message: Message) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None or (message.from_user and message.from_user.id != roles["initiator_id"]):
        await message.answer("Only initiator can delete methods.")
        return
    rows = list_custom_methods()
    if not rows:
        await message.answer("No deletable methods found.")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"🗑️ {name}", callback_data=f"delm:{mid}")] for mid, name in rows]
        + [[InlineKeyboardButton(text="🤨 Cancel", callback_data="delmcancel")]]
    )
    await message.answer("Choose a method to delete:", reply_markup=kb)


@router.callback_query(F.data.startswith("delm:"))
async def cb_delete_method_confirm(call: CallbackQuery) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None or call.from_user.id != roles["initiator_id"]:
        await call.answer("Only initiator can delete methods", show_alert=True)
        return
    try:
        mid = int(call.data.split(":")[1])
    except Exception:
        await call.answer("Invalid request", show_alert=True)
        return
    m = get_method_by_id(mid)
    if not m:
        await call.answer("Method not found", show_alert=True)
        return
    name = m["name"]
    if name in ALLOWED_METHODS:
        await call.answer("Cannot delete system method", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm delete", callback_data=f"delmcf:{mid}")],
            [InlineKeyboardButton(text="✖️ Cancel", callback_data="delmcancel")],
        ]
    )
    try:
        await call.message.edit_text(f"Delete method '{name}'? This cannot be undone.", reply_markup=kb)
    except Exception:
        await call.message.answer(f"Delete method '{name}'? This cannot be undone.", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "delmcancel")
async def cb_delete_method_cancel(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text("Deletion cancelled.")
    except Exception:
        await call.message.answer("Deletion cancelled.")
    await call.answer()


@router.callback_query(F.data.startswith("delmcf:"))
async def cb_delete_method_do(call: CallbackQuery) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None or call.from_user.id != roles["initiator_id"]:
        await call.answer("Only initiator can delete methods", show_alert=True)
        return
    try:
        mid = int(call.data.split(":")[1])
    except Exception:
        await call.answer("Invalid request", show_alert=True)
        return
    ok, msg = delete_method(mid)
    if ok:
        try:
            await call.message.edit_text("✅ Method deleted.")
        except Exception:
            await call.message.answer("✅ Method deleted.")
        await call.answer("Deleted")
    else:
        await call.answer(msg, show_alert=True)


# ========= Списки и экспорт =========
@router.message(Command("pending"))
async def cmd_pending(message: Message) -> None:
    rows = list_pending(limit=20)
    if not rows:
        await message.answer("No pending payments.")
        return
    text = "Pending payments (last 20):\n" + "\n".join(render_line(r) for r in rows)
    await message.answer(text)


@router.message(Command("my"))
async def cmd_my(message: Message) -> None:
    rows = list_user_payments(user_id=message.from_user.id, limit=20)
    if not rows:
        await message.answer("You have no recent payments.")
        return
    text = "Your recent payments (last 20):\n" + "\n".join(render_line(r) for r in rows)
    await message.answer(text)


@router.message(Command("pay"))
async def cmd_pay(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("#PAY-").isdigit():
        await message.answer("Usage: /pay <id>  (example: /pay 12)")
        return
    pid = int(parts[1].strip().lstrip("#PAY-"))
    p = get_payment_compact(pid)
    if not p:
        await message.answer("Payment not found.")
        return
    await message.answer(render_card(p))


@router.message(Command("export_csv"))
async def cmd_export_csv(message: Message) -> None:
    import os
    path = os.path.join(os.path.dirname(__file__), "payments_export.csv")
    export_payments_csv(path)
    await message.answer_document(FSInputFile(path), caption="Payments CSV export")


# ========= FSM =========
class PaymentForm(StatesGroup):
    amount = State()
    category_select = State()
    method_select = State()
    description = State()


@router.message(Command("newpay"))
async def newpay_start(message: Message, state: FSMContext) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None:
        set_initiator(message.from_user.id)
        roles = get_roles()
    if roles["initiator_id"] and (message.from_user and message.from_user.id != roles["initiator_id"]):
        await message.answer("Only initiator can create a request. Ask admin to change roles.")
        return
    await state.clear()
    await state.set_state(PaymentForm.amount)
    await message.answer(
        f"How much? ({CURRENCY})",
        reply_markup=kb_nav(back=False),
    )


@router.message(PaymentForm.amount)
async def newpay_amount(message: Message, state: FSMContext) -> None:
    txt = ((message.text or "").replace(",", ".").strip())
    try:
        amount = float(txt)
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer(
            f"Please enter a valid number. Example: 1250.00 ({CURRENCY})",
            reply_markup=kb_nav(back=False),
        )
        return
    await state.update_data(amount=amount)
    await state.set_state(PaymentForm.category_select)
    await message.answer("Select expense category:", reply_markup=category_kb())


@router.callback_query(F.data.startswith("cat:"))
async def cb_pick_category(call: CallbackQuery, state: FSMContext) -> None:
    code = call.data.split(":")[1]
    label = get_category_label_by_code(code)
    await state.update_data(category=label)
    await state.set_state(PaymentForm.method_select)
    await call.message.edit_text(
        f"Category: {label}\n\nSelect payment method:", reply_markup=methods_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("methodname:"))
async def cb_pick_method(call: CallbackQuery, state: FSMContext) -> None:
    method = call.data.split(":", 1)[1]
    if method not in {"Bank of Company", "USDT", "Cash"}:
        await call.answer("Unknown method", show_alert=True)
        return
    await state.update_data(method=method)
    await state.set_state(PaymentForm.description)
    await call.message.edit_text(
        f"Method: {method}\nNow enter description (any language):",
        reply_markup=kb_nav(back=True),
    )
    await call.answer()


@router.message(PaymentForm.description)
async def newpay_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()

    pid = create_payment(
        initiator_id=message.from_user.id,
        amount=data["amount"],
        currency=CURRENCY,
        method=data["method"],
        description=desc,
        category=(data.get("category") or "📦 Operating Expenses (Other)"),
    )
    p = get_payment(pid)

    group_id = get_group_id()
    if not group_id:
        await message.answer(
            "❗ Group is not set. Send /setup_here in the target group, then try /newpay again."
        )
        return
    sent = await message.bot.send_message(
        chat_id=group_id, text=render_card(p), reply_markup=kb_group_approve(pid)
    )
    set_group_message(pid, group_id, sent.message_id)

    await message.answer(f"Request #PAY-{pid} posted to the group for approval.")


# ========= Навигация формы (Back/Cancel) =========
@router.callback_query(F.data == "nav:cancel")
async def cb_nav_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await call.message.edit_text("❌ Form cancelled.")
    except Exception:
        await call.message.answer("❌ Form cancelled.")
    await call.answer()


@router.callback_query(F.data == "nav:back")
async def cb_nav_back(call: CallbackQuery, state: FSMContext) -> None:
    cur = await state.get_state()
    data = await state.get_data()
    if cur == PaymentForm.category_select.state:
        await state.set_state(PaymentForm.amount)
        amt = data.get("amount")
        prefix = f"(current: {amt}) " if amt is not None else ""
        try:
            await call.message.edit_text(
                f"{prefix}How much? ({CURRENCY})", reply_markup=kb_nav(back=False)
            )
        except Exception:
            await call.message.answer(
                f"{prefix}How much? ({CURRENCY})", reply_markup=kb_nav(back=False)
            )
    elif cur == PaymentForm.method_select.state:
        await state.set_state(PaymentForm.category_select)
        await call.message.edit_text("Select expense category:", reply_markup=category_kb())
    elif cur == PaymentForm.description.state:
        await state.set_state(PaymentForm.method_select)
        await call.message.edit_text("Select payment method:", reply_markup=methods_kb())
    else:
        await call.answer("Nothing to go back to.", show_alert=True)
        return
    await call.answer()


# ========= CALLBACKS ГРУППЫ (Approve/Reject) =========
@router.callback_query(F.data.startswith("approve:"))
async def cb_approve_payment(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])

    roles = get_roles()
    if call.from_user.id != roles["approver_id"]:
        await call.answer("You are not the designated approver", show_alert=True)
        return

    p = get_payment(pid)
    if not p:
        await call.answer("Payment not found", show_alert=True)
        return

    if p["status"] != "PENDING":
        await call.answer(f"Already finalized: {p['status']}", show_alert=True)
        return

    ok, msg = approve_payment(pid, approver_id=call.from_user.id)
    if not ok:
        await call.answer(msg, show_alert=True)
        return

    p = get_payment(pid)
    await call.message.edit_text(render_card(p))
    await call.answer("Approved ✅")

    try:
        await call.bot.send_message(p["initiator_id"], f"✅ Request #PAY-{pid} approved.")
    except Exception:
        pass

    try:
        if roles["viewer_id"] and roles["viewer_id"] != call.from_user.id:
            await call.bot.send_message(roles["viewer_id"], f"ℹ️ Payment approved for review:\n{render_card(p)}")
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])

    roles = get_roles()
    if call.from_user.id != roles["approver_id"]:
        await call.answer("You are not the designated approver", show_alert=True)
        return

    ok, msg = reject_payment(pid, approver_id=call.from_user.id)
    if not ok:
        await call.answer(msg, show_alert=True)
        return

    p = get_payment(pid)
    await call.message.edit_text(render_card(p))
    await call.answer("Rejected ❌")

    try:
        await call.bot.send_message(p["initiator_id"], f"❌ Request #PAY-{pid} rejected.")
    except Exception:
        pass

    try:
        vid = roles.get("viewer_id")
        if vid and vid not in (call.from_user.id, p["initiator_id"]):
            await call.bot.send_message(vid, f"ℹ️ Payment rejected for review:\n{render_card(p)}")
    except Exception:
        pass


# ========= Эхо =========
@router.message()
async def any_message(message: Message) -> None:
    if message.chat.type in ("group", "supergroup"):
        return
    await message.answer(
        "Use /ping or /newpay. Lists: /pending, /my, /pay <id>. Export: /export_csv. "
        "Setup: /setup_here, /set_all_me, /set_initiator <id>, /set_approver <id>, /set_viewer <id>, /roles, /ver"
    )