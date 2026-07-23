from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf

from app.chat import bp
from app.chat.forms import ChatPageForm, DirectStartForm
from app.chat.policy import SOCKET_IO_INTEGRITY
from app.chat.services import (
    DirectConversationResult,
    get_direct_conversation,
    get_message_history,
    list_direct_conversations,
    start_direct_conversation,
)
from app.extensions import limiter
from app.security import authenticated_user_rate_limit_key, no_store


def _valid_page() -> int | None:
    form = ChatPageForm(request.args)
    if not form.validate():
        return None
    return form.page.data or 1


@bp.get("")
@login_required
@limiter.limit("60 per minute")
@no_store
def global_chat():
    page = _valid_page()
    if page is None:
        abort(400)
    history = get_message_history(
        conversation_id=None,
        page=page,
        per_page=current_app.config["CHAT_HISTORY_PER_PAGE"],
    )
    return render_template(
        "chat/global.html",
        history=history,
        live_enabled=page == 1,
        socket_csrf_token=generate_csrf(),
        socket_io_integrity=SOCKET_IO_INTEGRITY,
    )


@bp.get("/direct")
@login_required
@limiter.limit("60 per minute")
@no_store
def direct_index():
    page = _valid_page()
    if page is None:
        abort(400)
    conversations = list_direct_conversations(
        user_id=current_user.id,
        page=page,
        per_page=current_app.config["CHAT_CONVERSATIONS_PER_PAGE"],
    )
    return render_template(
        "chat/direct_index.html",
        conversations=conversations,
        form=DirectStartForm(),
    )


@bp.post("/direct/start")
@login_required
@limiter.limit("20 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def direct_start():
    form = DirectStartForm()
    if not form.validate_on_submit():
        flash("대화 상대를 확인할 수 없습니다.", "error")
        return redirect(url_for("chat.direct_index"), code=303)

    result, conversation_id = start_direct_conversation(
        current_user, form.username.data
    )
    if result in {
        DirectConversationResult.TARGET_UNAVAILABLE,
        DirectConversationResult.SELF_TARGET,
    }:
        flash("대화 상대를 확인할 수 없습니다.", "error")
        return redirect(url_for("chat.direct_index"), code=303)
    if result is DirectConversationResult.DATABASE_ERROR or conversation_id is None:
        flash("대화를 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")
        return redirect(url_for("chat.direct_index"), code=303)
    return redirect(
        url_for("chat.direct_chat", conversation_id=conversation_id), code=303
    )


@bp.get("/direct/<uuid:conversation_id>")
@login_required
@limiter.limit("60 per minute")
@no_store
def direct_chat(conversation_id):
    page = _valid_page()
    if page is None:
        abort(400)
    canonical_id = str(conversation_id)
    conversation = get_direct_conversation(canonical_id, current_user.id)
    if conversation is None:
        abort(404)
    history = get_message_history(
        conversation_id=canonical_id,
        page=page,
        per_page=current_app.config["CHAT_HISTORY_PER_PAGE"],
    )
    return render_template(
        "chat/direct.html",
        conversation=conversation,
        history=history,
        live_enabled=page == 1 and conversation.counterpart_is_active,
        socket_csrf_token=generate_csrf(),
        socket_io_integrity=SOCKET_IO_INTEGRITY,
    )
