import asyncio
from pathlib import Path

from creart import create
from graia.ariadne.app import Ariadne
from graia.ariadne.event.message import GroupMessage, MessageEvent
from graia.ariadne.event.mirai import BotInvitedJoinGroupRequestEvent, MemberJoinRequestEvent
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.message.element import At, Source
from graia.ariadne.message.parser.twilight import Twilight, UnionMatch, SpacePolicy, ElementMatch, FullMatch, \
    ElementResult
from graia.ariadne.model import Group, Member
from graia.ariadne.util.interrupt import FunctionWaiter
from graia.ariadne.util.saya import listen, decorate, dispatch
from graia.saya import Channel, Saya
from loguru import logger

from core.config import GlobalConfig
from core.control import (
    Permission,
    Function,
    FrequencyLimitation,
    Distribute,
    QuoteReply
)
from core.models import (
    saya_model,
    response_model
)

module_controller = saya_model.get_module_controller()
account_controller = response_model.get_acc_controller()
global_config = create(GlobalConfig)
saya = Saya.current()
channel = Channel.current()
channel.name("QQ群管")
channel.description("简易的qq群管理功能")
channel.author("13")
channel.metadata = module_controller.get_metadata_from_path(Path(__file__))


# 处理BOT被邀请加群事件
@listen(BotInvitedJoinGroupRequestEvent)
async def invited_event(app: Ariadne, event: BotInvitedJoinGroupRequestEvent):
    """处理邀请
    """
    if await Permission.require_user_perm(event.source_group, event.supplicant, Permission.BotAdmin):
        await event.accept('已同意您的邀请~')
        return await app.send_message(await app.get_group(global_config.test_group), MessageChain(
            f"成员{event.nickname}({event.supplicant})邀请bot加入群:\n{event.group_name}({event.source_group})\n"
            f'已自动同意该管理的邀请'
        ))
    group = await app.get_group(global_config.test_group)
    if group is None:
        member = await app.get_friend(global_config.Master)
        bot_message = await app.send_message(member, MessageChain(
            f"成员{event.nickname}({event.supplicant})邀请bot加入群:\n{event.group_name}({event.source_group})\n"
            f'是否同意该申请，请在1小时内回复“y”或“n”'
        ))
    else:
        bot_message = await app.send_message(group, MessageChain(
            f"成员{event.nickname}({event.supplicant})邀请bot加入群:\n{event.group_name}({event.source_group})\n"
            f'是否同意该申请，请在1小时内回复“y”或“n”'
        ))

    async def waiter(waiter_member: Member, waiter_message: MessageChain, waiter_group: Group,
                     event_waiter: GroupMessage):
        if await Permission.require_user_perm(waiter_group.id, waiter_member.id,
                                              Permission.GroupAdmin) and group.id == waiter_group.id \
                and event_waiter.quote and event_waiter.quote.id == bot_message.id:
            saying = waiter_message.replace(At(app.account), "").display.strip()
            if saying == 'y':
                return True, waiter_member.id
            elif saying == 'n':
                return False, waiter_member.id
            elif saying.startswith("n"):
                saying.replace("n", "")
                return False, waiter_member.id

    try:
        result, admin = await FunctionWaiter(waiter, [GroupMessage]).wait(timeout=3600)
    except asyncio.exceptions.TimeoutError:
        await event.reject("拒绝了你的入群邀请!")
        return await app.send_message(group, MessageChain(
            f'处理 {event.nickname}({event.supplicant}) 的入群邀请已自动拒绝'))

    if result:
        await event.accept('已同意您的邀请~')  # 同意入群
        await app.send_message(group, MessageChain(
            f'已同意 {event.nickname}({event.supplicant}) 的入群邀请'))
    else:
        await event.reject(f'BOT拒绝了你的入群邀请!')  # 拒绝
        await app.send_message(group, MessageChain(
            f'已拒绝 {event.nickname}({event.supplicant}) 的入群邀请'))


# 入群审核
@listen(MemberJoinRequestEvent)
async def join_handle(app: Ariadne, event: MemberJoinRequestEvent):
    """
    :param app: 实例
    :param event: 有人申请加群
    :return:
    """
    group = await app.get_group(event.source_group)
    # 先解析加群信息
    application_message = event.message
    application_answer = application_message[application_message.find("答案：") + 3:] \
        if application_message.find("答案：") != -1 else application_message
    # 然后发送消息到群里,如果bot有群管理权限则用waiter，超时时间为20分钟，发送申请消息
    bot_msg = await app.send_message(
        group,
        MessageChain(f"收到来自{event.nickname}({event.supplicant})的加群申请,信息如下:"
                     f"\n{application_message}"
                     f"\n‘回复’本消息‘y’可同意该申请"
                     f"\n‘回复’本消息其他文字可作为理由拒绝"
                     f"\n请在十分钟内处理")
    )

    async def waiter(waiter_member: Member, waiter_message: MessageChain, waiter_group: Group,
                     event_waiter: GroupMessage):
        try:
            await app.get_member(waiter_group, event.supplicant)
            join_judge = True
        except:
            join_judge = False
        if not join_judge:
            if event.source_group == waiter_group.id and event_waiter.quote and event_waiter.quote.id == bot_msg.id \
                    and await Permission.require_user_perm(waiter_group.id, waiter_member.id, Permission.GroupAdmin):
                saying = waiter_message.replace(At(app.account), "").display.strip()
                if saying == 'y':
                    return True, None
                else:
                    return False, saying

    # 接收回复消息，如果为y则同意，如果不为y则以该消息拒绝
    try:
        return_info = await FunctionWaiter(waiter, [GroupMessage]).wait(timeout=600)
    except asyncio.exceptions.TimeoutError:
        try:
            return await app.get_member(group, event.supplicant)
        except:
            return await app.send_message(
                group,
                MessageChain(f'注意:由于超时未审核，处理 {event.nickname}({event.supplicant}) 的入群请求已失效')
            )

    if return_info:
        result, reason = return_info
    else:
        result = reason = None
    if result:
        await event.accept()  # 同意入群
        return await app.send_message(group, MessageChain(
            f'已同意 {event.nickname}({event.supplicant}) 的入群请求'), )
    elif result is False:
        await event.reject(reason if reason else "")  # 拒绝入群
        return await app.send_message(group, MessageChain(
            f'已拒绝 {event.nickname}({event.supplicant}) 的入群请求'
        ))
    else:
        pass


# 添加群精华消息
@listen(GroupMessage)
@decorate(
    Distribute.require(),
    QuoteReply.require(),
    Permission.user_require(Permission.GroupAdmin, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module)
)
@dispatch(
    Twilight([
        "at" @ ElementMatch(At, optional=True).space(SpacePolicy.PRESERVE),
        UnionMatch("加精", "设精")
    ])
)
async def set_essence(app: Ariadne, group: Group, event: MessageEvent, source: Source):
    target_app, target_group = await account_controller.get_app_from_total_groups(group.id, "Administrator")
    if not (target_app and target_group):
        return await app.send_message(group, MessageChain(
            f"bot权限不足!/获取群权限信息失败!"
        ), quote=source)
    app = target_app
    group = target_group
    quote_id = event.quote.id
    try:
        await app.set_essence(quote_id)
    except Exception as e:
        logger.error(e)
        return await app.send_message(group, MessageChain(
            f"出错力!"
        ), quote=source)

    return await app.send_message(group, MessageChain(
        f"加精成功"
    ), quote=source)


# TODO 撤回 quote.id   recall
@listen(GroupMessage)
@decorate(
    Distribute.require(),
    QuoteReply.require(),
    Permission.user_require(Permission.GroupAdmin, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module)
)
@dispatch(
    Twilight([
        "at" @ ElementMatch(At, optional=True).space(SpacePolicy.PRESERVE),
        FullMatch("撤回")
    ])
)
async def recall(app: Ariadne, group: Group, event: GroupMessage, source: Source):
    quote_id = event.quote.id
    bot_member = await app.get_member(group, app.account)
    if bot_member.permission.name == "Member" and event.quote.sender_id != bot_member.id:
        return await app.send_message(group, MessageChain(
            f"bot权限不足!"
        ), quote=source)
    try:
        await app.recall_message(quote_id)
        return await app.send_message(group, MessageChain(
            f"撤回成功"
        ), quote=source)
    except Exception as e:
        logger.error(e)
        return await app.send_message(group, MessageChain(
            f"撤回出错啦,找管理员看看吧~"
        ), quote=source)


# TODO 禁言 @qq 禁言
@listen(GroupMessage)
@decorate(
    Distribute.require(),
    Permission.user_require(Permission.GroupAdmin, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module)
)
@dispatch(
    Twilight([
        "at" @ ElementMatch(At, optional=True).space(SpacePolicy.PRESERVE),
        FullMatch("禁言")
    ])
)
async def mute(app: Ariadne, group: Group, event: GroupMessage, source: Source, at: ElementResult):
    target_app, target_group = await account_controller.get_app_from_total_groups(group.id, "Administrator")
    if not (target_app and target_group):
        return await app.send_message(group, MessageChain(
            f"bot权限不足!/获取群权限信息失败!"
        ), quote=source)
    target_perm = await Permission.get_user_perm_byID(group.id, event.quote.sender_id)
    bot_perm = await Permission.get_user_perm_byID(group.id, event.quote.sender_id)
    if target_perm >= bot_perm:
        return await app.send_message(group, MessageChain(
            f"bot权限不足!(target_perm:{target_perm}/bot_perm:{bot_perm})"
        ), quote=source)
    app: Ariadne = target_app
    group: Group = target_group
    if at.matched:
        _target: At = at.result
        _target = _target.target
        try:
            await app.mute_member(group, _target, 120)
            return await app.send_message(group, MessageChain(f"已设置{_target}2分钟的禁言!"))
        except Exception as e:
            logger.error(e)
            return await app.send_message(group, MessageChain(
                f"设置禁言出错啦!"
            ), quote=source)
    if event.quote:
        try:
            await app.mute_member(group, event.quote.sender_id, 120)
            return await app.send_message(group, MessageChain(f"已设置{event.quote.sender_id}2分钟的禁言!"))
        except Exception as e:
            logger.error(e)
            return await app.send_message(group, MessageChain(
                f"设置禁言出错啦!"
            ), quote=source)
