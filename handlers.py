from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from generators import (
    get_group_id, set_group_id, get_roles, set_all_me, set_initiator,
    list_methods, create_approved_payment, get_payment,
    list_pending, list_user_payments, get_payment_compact, export_payments_csv,
    set_approver, set_viewer,
    get_config,
)
from sheet_logger import log_approval_to_sheet
from memory_store import put_staged, pop_staged, get_staged

router = Router()

CURRENCY = "THB"  # фиксированная валюта

# ========= Категории расходов =========
CATEGORIES = [
    ("📮 Rent & Utilities", "rent"),
    ("🥳 Salaries & Employee Payments", "salaries"),
    ("🛵 Transport & Logistics", "transport"),
    ("⚡️ Marketing & Advertising", "marketing"),
    ("👨🏽‍💻 IT & Services", "it"),
    ("🧐 Operating Expenses (Other)", "operating"),
]

def get_category_label_by_code(code: str) -> str:
    for label, c in CATEGORIES:
        if c == code:
            return label
    return "🧐 Operating Expenses (Other)"

# ========= Клавиатуры =========
def kb_nav(back: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if back:
        rows.append([InlineKeyboardButton(text="👈🏼 Back", callback_data="nav:back")])
    rows.append([InlineKeyboardButton(text="🙅🏽‍♂️ Cancel", callback_data="nav:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def category_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"cat:{code}")] for label, code in CATEGORIES]
    rows.append([InlineKeyboardButton(text="👈🏼 Back", callback_data="nav:back"),
                 InlineKeyboardButton(text="🙅🏽‍♂️ Cancel", callback_data="nav:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def methods_kb(include_nav: bool = True) -> InlineKeyboardMarkup:
    rows = []
    allowed = {"Bank of Company", "USDT", "Cash"}
    for mid, name in list_methods():
        if name in allowed:
            rows.append([InlineKeyboardButton(text=name, callback_data=f"methodid:{mid}")])
    if include_nav:
        rows.append([
            InlineKeyboardButton(text="👈🏼 Back", callback_data="nav:back"),
            InlineKeyboardButton(text="🙅🏽‍♂️ Cancel", callback_data="nav:cancel")
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# legacy keyboard retained for backward compatibility (old pending items if any)
def kb_group_approve(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔋 Approve", callback_data=f"approve_legacy:{pid}"),
        InlineKeyboardButton(text="🪫 Reject", callback_data=f"reject_legacy:{pid}")
    ]])

# ========= Утилиты =========
def fmt_amount(val: float) -> str:
    if float(val).is_integer():
        return f"{int(val):,}".replace(",", ".")
    s = f"{val:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return s

def render_card(p: dict) -> str:
    category_text = p.get("category") or "🧐 Operating Expenses (Other)"
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
    """Короткая строка для списков."""
    cat = row.get("category") or "🧐 Operating Expenses (Other)"
    return f"#PAY-{row['id']} — {fmt_amount(row['amount'])} {row['currency']} — {row['method']} — {cat} — {row['status']} — {row['created_at']}"

# ========= Базовые команды =========
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "✅ Bot online.\n"
        "Commands: /ping, /newpay, /methods, /pending, /my, /pay <id>, /export_csv, /whoami, /roles, /set_all_me, /set_initiator <id>, /set_approver <id>, /set_viewer <id>, /setup_here (in group), /ver"
    )

@router.message(Command("ver"))
async def cmd_ver(message: Message) -> None:
    await message.answer("build: sqlite-payments-lists-004")  # bumped

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
    """
    Использование: /set_initiator <id>
    Менять может только текущий initiator (или secondary_initiator).
    Если initiатор ещё не задан — первый вызов команды создаст его.
    """
    roles = get_roles()
    current_init = roles["initiator_id"]

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /set_initiator <id>")
        return

    new_init = int(parts[1])

    # Если инициатор уже задан — менять может только он или второй инициатор
    sec = get_config("secondary_initiator_id", None, int)
    allowed = {current_init, sec}
    if None in allowed:
        allowed.discard(None)
    if current_init is not None and message.from_user.id not in allowed:
        await message.answer("Only current initiators can change initiator ID.")
        return

    set_initiator(new_init)
    await message.answer(f"✅ Initiator set to {new_init}")

@router.message(Command("set_approver"))
async def cmd_set_approver_cmd(message: Message) -> None:
    """
    Использование: /set_approver <id>
    Менять может текущий initiator или secondary_initiator.
    """
    roles = get_roles()
    sec = get_config("secondary_initiator_id", None, int)
    allowed = {roles.get("initiator_id"), sec}
    if None in allowed:
        allowed.discard(None)
    if not allowed or message.from_user.id not in allowed:
        await message.answer("Only initiators can change approver. Ask admin to change roles.")
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
    """
    Использование: /set_viewer <id>
    Менять может текущий initiator или secondary_initiator.
    """
    roles = get_roles()
    sec = get_config("secondary_initiator_id", None, int)
    allowed = {roles.get("initiator_id"), sec}
    if None in allowed:
        allowed.discard(None)
    if not allowed or message.from_user.id not in allowed:
        await message.answer("Only initiators can change viewer. Ask admin to change roles.")
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
    parts = message.text.split(maxsplit=1)
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
    receipt = State()      # now BEFORE description
    description = State()  # moved after receipt

@router.message(Command("newpay"))
async def newpay_start(message: Message, state: FSMContext) -> None:
    roles = get_roles()
    if roles["initiator_id"] is None:
        set_initiator(message.from_user.id)
        roles = get_roles()
    # allow primary and secondary initiators
    sec = get_config("secondary_initiator_id", None, int)
    allowed = {roles.get("initiator_id"), sec}
    if None in allowed:
        allowed.discard(None)
    if message.from_user.id not in allowed:
        await message.answer("Only initiators can create a request. Ask admin to change roles.")
        return
    await state.clear()
    await state.set_state(PaymentForm.amount)
    await message.answer(
        f"How much? ({CURRENCY})",
        reply_markup=kb_nav(back=False)  # только Cancel
    )

@router.message(PaymentForm.amount)
async def newpay_amount(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").replace(",", ".").strip()
    try:
        amount = float(txt)
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer(f"Please enter a valid number. Example: 1250.00 ({CURRENCY})", reply_markup=kb_nav(back=False))
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
    await call.message.edit_text(f"Category: {label}\n\nSelect payment method:", reply_markup=methods_kb(include_nav=True))
    await call.answer()

@router.callback_query(F.data.startswith("methodname:"))
async def cb_pick_method(call: CallbackQuery, state: FSMContext) -> None:
    method = call.data.split(":", 1)[1]
    # Валидация против фиксированного набора
    if method not in {"Bank of Company", "USDT", "Cash"}:
        await call.answer("Unknown method", show_alert=True)
        return
    await state.update_data(method=method)
    await state.set_state(PaymentForm.receipt)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Skip", callback_data="receipt:skip")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="nav:back"), InlineKeyboardButton(text="✖️ Cancel", callback_data="nav:cancel")]
    ])
    await call.message.edit_text(f"Method: {method}\nAttach receipt (photo/document) or Skip.", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("methodid:"))
async def cb_pick_method_by_id(call: CallbackQuery, state: FSMContext) -> None:
    try:
        mid = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Bad method", show_alert=True)
        return
    from generators import get_method_by_id
    m = get_method_by_id(mid)
    if not m or m["name"] not in {"Bank of Company", "USDT", "Cash"}:
        await call.answer("Unknown method", show_alert=True)
        return
    method = m["name"]
    await state.update_data(method=method)
    await state.set_state(PaymentForm.receipt)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Skip", callback_data="receipt:skip")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="nav:back"), InlineKeyboardButton(text="✖️ Cancel", callback_data="nav:cancel")]
    ])
    await call.message.edit_text(f"Method: {method}\nAttach receipt (photo/document) or Skip.", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "receipt:skip")
async def cb_receipt_skip(call: CallbackQuery, state: FSMContext) -> None:
    # skip receipt and ask description
    await state.update_data(receipt_file=None, receipt_kind=None)
    await state.set_state(PaymentForm.description)
    await call.message.edit_text("Enter description (any language):", reply_markup=kb_nav(back=True))
    await call.answer()

@router.message(PaymentForm.receipt, F.photo)
async def newpay_receipt_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1] if message.photo else None
    fid = photo.file_id if photo else None
    await state.update_data(receipt_file=fid, receipt_kind="photo")
    await state.set_state(PaymentForm.description)
    await message.answer("Receipt saved. Now enter description:", reply_markup=kb_nav(back=True))

@router.message(PaymentForm.receipt, F.document)
async def newpay_receipt_document(message: Message, state: FSMContext) -> None:
    doc = message.document
    fid = doc.file_id if doc else None
    await state.update_data(receipt_file=fid, receipt_kind="document")
    await state.set_state(PaymentForm.description)
    await message.answer("Receipt saved. Now enter description:", reply_markup=kb_nav(back=True))

@router.message(PaymentForm.receipt)
async def newpay_receipt_other(message: Message, state: FSMContext) -> None:
    await message.answer("Send photo/document or press Skip.")

@router.message(PaymentForm.description)
async def newpay_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    await state.update_data(description=desc)
    data = await state.get_data()
    group_id = get_group_id()
    if not group_id:
        await message.answer("❗ Group is not set. Send /setup_here in the target group, then try again.")
        await state.clear()
        return
    import time
    temp_id = int(time.time())  # simplistic unique id
    staged = {
        "initiator_id": message.from_user.id,
        "amount": data["amount"],
        "currency": CURRENCY,
        "method": data["method"],
        "description": desc,
        "category": data.get("category") or "🧐 Operating Expenses (Other)",
        "receipt_file": data.get("receipt_file"),
        "receipt_kind": data.get("receipt_kind"),
    }
    put_staged(temp_id, staged)
    preview = (
        f"#PAY-STAGED-{temp_id}\n• {fmt_amount(staged['amount'])} {CURRENCY}\n• {staged['method']}\n" \
        f"• {staged['category']}\n\n" \
        f"• Description: {desc}\n\nStatus: WAITING APPROVAL (not saved)\nInitiator: {message.from_user.id}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_staged:{temp_id}"), InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_staged:{temp_id}")]])
    receipt_file = staged.get('receipt_file')
    receipt_kind = staged.get('receipt_kind')
    try:
        if receipt_file and receipt_kind == 'photo':
            await message.bot.send_photo(chat_id=group_id, photo=receipt_file, caption=preview, reply_markup=kb)
        elif receipt_file and receipt_kind == 'document':
            await message.bot.send_document(chat_id=group_id, document=receipt_file, caption=preview, reply_markup=kb)
        else:
            await message.bot.send_message(chat_id=group_id, text=preview, reply_markup=kb)
    except Exception:
        await message.bot.send_message(chat_id=group_id, text=preview, reply_markup=kb)
    await message.answer("Staged request posted for approval. It will be saved only if approved.")

@router.callback_query(F.data.startswith("approve_staged:"))
async def cb_approve_staged(call: CallbackQuery) -> None:
    roles = get_roles()
    if call.from_user.id != roles.get('approver_id'):
        await call.answer("Not approver", show_alert=True)
        return
    temp_id = int(call.data.split(":")[1])
    staged = get_staged(temp_id)
    if not staged:
        await call.answer("Staged data missing", show_alert=True)
        return
    pid = create_approved_payment(
        initiator_id=staged['initiator_id'],
        approver_id=call.from_user.id,
        amount=staged['amount'],
        currency=staged['currency'],
        method=staged['method'],
        description=staged['description'],
        category=staged['category']
    )
    pop_staged(temp_id)
    p = get_payment(pid)
    # Try to update caption/text with final card (may fail for some media types)
    try:
        await call.message.edit_caption(render_card(p))
    except Exception:
        try:
            await call.message.edit_text(render_card(p))
        except Exception:
            pass
    # Additionally send a new separate message with full data so it is always visible even if caption edit fails or only photo shown
    try:
        gid = get_group_id()
        if gid:
            await call.bot.send_message(gid, render_card(p))
    except Exception:
        pass
    await call.answer("Approved ✅")
    try:
        log_approval_to_sheet(p)
    except Exception:
        pass
    try:
        await call.bot.send_message(p['initiator_id'], f"✅ Request #PAY-{pid} approved.")
    except Exception:
        pass

@router.callback_query(F.data.startswith("reject_staged:"))
async def cb_reject_staged(call: CallbackQuery) -> None:
    roles = get_roles()
    if call.from_user.id != roles.get('approver_id'):
        await call.answer("Not approver", show_alert=True)
        return
    temp_id = int(call.data.split(":")[1])
    staged = get_staged(temp_id)
    if not staged:
        await call.answer("Nothing to discard", show_alert=True)
        return
    # Prepare a full info message before removing staged
    full_info = (
        f"#PAY-STAGED-{temp_id}\n• {fmt_amount(staged['amount'])} {staged['currency']}\n"\
        f"• {staged['method']}\n• {staged['category']}\n\n"\
        f"• Description: {staged['description']}\n\nStatus: REJECTED (not saved)\nInitiator: {staged['initiator_id']}\nRejected by: {call.from_user.id}"
    )
    pop_staged(temp_id)
    try:
        await call.message.edit_caption("Staged request rejected.")
    except Exception:
        try:
            await call.message.edit_text("Staged request rejected.")
        except Exception:
            pass
    # Send separate full data message for history
    try:
        gid = get_group_id()
        if gid:
            await call.bot.send_message(gid, full_info)
    except Exception:
        pass
    await call.answer("Discarded ❌")
    try:
        await call.bot.send_message(staged['initiator_id'], "❌ Your staged request was rejected (not saved).")
    except Exception:
        pass

@router.callback_query(F.data == "nav:back")
async def cb_nav_back(call: CallbackQuery, state: FSMContext) -> None:
    cur = await state.get_state()
    data = await state.get_data()
    if cur == PaymentForm.method_select.state:
        # back to category
        await state.set_state(PaymentForm.category_select)
        await call.message.edit_text("Select expense category:", reply_markup=category_kb())
    elif cur == PaymentForm.receipt.state:
        await state.set_state(PaymentForm.method_select)
        await call.message.edit_text("Select payment method:", reply_markup=methods_kb(include_nav=True))
    elif cur == PaymentForm.description.state:
        await state.set_state(PaymentForm.receipt)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Skip", callback_data="receipt:skip")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="nav:back"), InlineKeyboardButton(text="✖️ Cancel", callback_data="nav:cancel")]
        ])
        await call.message.edit_text("Attach receipt (photo/document) or Skip.", reply_markup=kb)
    else:
        await call.answer("Nothing to go back to.", show_alert=True)
        return
    await call.answer()

# ========= Эхо =========
@router.message()
async def any_message(message: Message) -> None:
    # В группах и супер-группах молчим
    if message.chat.type in ("group", "supergroup"):
        return
    # В личке показываем подсказку
    await message.answer(
        "Use /ping or /newpay. Lists: /pending, /my, /pay <id>. Export: /export_csv. "
        "Setup: /setup_here, /set_all_me, /set_initiator <id>, /set_approver <id>, /set_viewer <id>, /roles, /ver"
    )