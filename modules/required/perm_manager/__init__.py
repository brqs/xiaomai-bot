from pathlib import Path

from creart import create
from graia.ariadne.app import Ariadne
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.event.mirai import MemberLeaveEventQuit
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.message.element import Image, Source
from graia.ariadne.message.parser.twilight import (
    Twilight,
    FullMatch,
    ParamMatch,
    UnionMatch,
    RegexResult,
    WildcardMatch
)
from graia.ariadne.model import Group, Member
from graia.ariadne.util.saya import listen, dispatch, decorate
from graia.saya import Channel, Saya

from core.bot import Umaru
from core.config import GlobalConfig
from core.control import (
    Permission,
    Function,
    FrequencyLimitation,
    Distribute
)
from core.models import (
    saya_model,
    response_model
)
from core.orm import orm
from core.orm.tables import MemberPerm, GroupPerm
from utils.UI import *
from utils.image import get_user_avatar_url
from .utils import get_targets

config = create(GlobalConfig)
core = create(Umaru)

module_controller = saya_model.get_module_data()
account_controller = response_model.get_acc_data()

saya = Saya.current()
channel = Channel.current()
channel.name("SayaManager")
channel.description("负责插件管理(必须插件)")
channel.author("13")
channel.metadata = module_controller.get_metadata_from_file(Path(__file__))


# >=64可修改当前群的用户权限
@listen(GroupMessage)
@decorate(
    Permission.user_require(Permission.GroupOwner, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module),
    Distribute.require()
)
@dispatch(
    Twilight([
        FullMatch("修改权限"),
        "group_id" @ ParamMatch(optional=True),
        "perm" @ UnionMatch("64", "32", "16", "0"),
        "member_id" @ WildcardMatch()
        # 示例: 修改权限 群号 perm
    ])
)
async def change_user_perm(
        app: Ariadne, group: Group, event: GroupMessage,
        group_id: RegexResult,
        perm: RegexResult,
        member_id: RegexResult,
        source: Source
):
    """
    修改用户权限
    """
    group_id = int(group_id.result.display) if group_id.matched else group.id
    targets = get_targets(member_id.result)
    try:
        perm = int(perm.result.display)
    except:
        return await app.send_message(group, MessageChain(
            f"请检查输入的权限(64/32/16/0)"
        ), quote=source)
    # 修改其他群组的权限判假
    if group_id != group.id:
        if (user_level := await Permission.get_user_perm(event)) < Permission.Admin:
            return await app.send_message(event.sender.group, MessageChain(
                f"权限不足!(你的权限:{user_level}/需要权限:{Permission.Admin})"
            ), quote=source)
        target_app = await account_controller.get_app_from_total_groups(group_id)
        target_group = await target_app.get_group(group_id)
    else:
        target_app = app
        target_group = group
    error_targets = []
    for target in targets:
        if await Permission.get_user_perm(event) < (
                target_perm := await Permission.get_user_perm_byID(target_group.id, target)):
            error_targets.append((target, f"无法降级{target}({target_perm})"))
        elif await target_app.get_member(target_group, target) is None:
            error_targets.append((target, f"没有在群{target_group}找到群成员"))
        elif await Permission.get_user_perm_byID(target_group.id, target) == Permission.Admin:
            error_targets.append((target, f"无法直接通过该指令修改BOT管理权限"))
        else:
            await orm.insert_or_update(
                table=MemberPerm,
                condition=[
                    MemberPerm.qq == target,
                    MemberPerm.group_id == target_group.id
                ],
                data={
                    "group_id": target_group.id,
                    "qq": target,
                    "perm": perm
                }
            )
    response_text = f"共解析{len(targets)}个目标\n其中{len(targets) - len(error_targets)}个执行成功,{len(error_targets)}个失败"
    if error_targets:
        response_text += "\n\n失败目标:"
        for i in error_targets:
            response_text += f"\n{i[0]}-{i[1]}"
    await app.send_message(group, response_text, quote=source)


# 自动删除退群的权限
@listen(MemberLeaveEventQuit)
async def auto_del_perm(app: Ariadne, group: Group, member: Member):
    target_perm = await Permission.get_user_perm_byID(group.id, member.id)
    await orm.delete(
        table=MemberPerm,
        condition=[
            MemberPerm.qq == member.id,
            MemberPerm.group_id == group.id
        ]
    )
    if Permission.GroupOwner >= target_perm >= Permission.GroupAdmin:
        return await app.send_message(group, f"已自动删除退群成员{member.name}({member.id})的权限")


# >=128可修改群权限
@listen(GroupMessage)
@decorate(
    Permission.user_require(Permission.Admin, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module),
    Distribute.require()
)
@dispatch(
    Twilight([
        FullMatch("修改群权限"),
        "group_id" @ ParamMatch(optional=True),
        "perm" @ UnionMatch("3", "2", "1", "0"),
        # 示例: 修改权限 群号 perm
    ])
)
async def change_group_perm(
        app: Ariadne,
        group: Group,
        group_id: RegexResult,
        perm: RegexResult,
        source: Source
):
    group_id = int(group_id.result.display) if group_id.matched else group.id
    try:
        perm = int(perm.result.display)
    except:
        return await app.send_message(group, MessageChain(
            f"请检查输入的权限(3/2/1/0)"
        ), quote=source)
    target_app = await account_controller.get_app_from_total_groups(group_id)
    target_group: Group = await target_app.get_group(group_id)
    if not target_group:
        return await app.send_message(group, MessageChain(
            f"没有找到目标群:{group_id}"
        ), quote=source)
    if target_group.id == config.test_group:
        return await app.send_message(group, MessageChain(
            f"无法通过该指令修改测试群({target_group.id})权限!"
        ), quote=source)
    await orm.insert_or_update(
        GroupPerm,
        {"group_id": target_group.id, "group_name": target_group.name, "active": True, "perm": perm},
        [
            GroupPerm.group_id == group.id
        ]
    )
    return await app.send_message(group, MessageChain(
        f"已修改群{target_group.name}({target_group.id})权限为{perm}"
    ), quote=source)


@listen(GroupMessage)
@decorate(
    Permission.user_require(Permission.GroupAdmin, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module),
    Distribute.require()
)
@dispatch(
    Twilight([
        UnionMatch("perm list", "权限列表"),
        "group_id" @ ParamMatch(optional=True),
        # 示例: perm list
    ])
)
async def get_perm_list(app: Ariadne, group: Group, group_id: RegexResult, source: Source, event: GroupMessage):
    group_id = int(group_id.result.display) if group_id.matched else group.id
    if group_id != group.id:
        if (user_level := await Permission.get_user_perm(event)) < Permission.Admin:
            return await app.send_message(event.sender.group, MessageChain(
                f"权限不足!(你的权限:{user_level}/需要权限:{Permission.Admin})"
            ), quote=source)
        target_app = await account_controller.get_app_from_total_groups(group_id)
        target_group = await target_app.get_group(group_id)
    else:
        target_app = app
        target_group = group
    # 查询权限组-当权限>=128时 可以查询其他群的
    """
    [ (perm, qq) ]
    """
    perm_list = await Permission.get_users_perm_byID(group_id)
    perm_dict = {}
    for member in await app.get_member_list(group_id):
        for item in perm_list:
            perm_dict[item[1]] = item[0]
        if member.id not in perm_dict and Permission.perm_dict[member.permission.name] != 16:
            perm_dict[member.id] = Permission.perm_dict[member.permission.name]
    perm_dict = dict(sorted(perm_dict.items(), key=lambda x: x[1], reverse=True))
    """
    perm_dict = {
        qq: perm
    }
    """
    perm_list_column = [ColumnTitle(title="权限列表")]
    for member_id in perm_dict:
        try:
            member_item = await target_app.get_member(target_group, member_id)
        except:
            member_item = None
        perm_list_column.append(
            ColumnUserInfo(
                name=f"{member_item.name}({member_id})" if member_item else member_id,
                description=perm_dict[member_id],
                avatar=await get_user_avatar_url(member_id)
            )
        )
    perm_list_column = [Column(elements=perm_list_column[i: i + 20]) for i in range(0, len(perm_list_column), 20)]
    return await app.send_message(group, MessageChain(
        Image(data_bytes=await OneMockUI.gen(
            GenForm(columns=perm_list_column, color_type="dark")
        ))
    ), quote=source)


# 增删bot管理
@listen(GroupMessage)
@decorate(
    Permission.user_require(Permission.Master),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module),
    Distribute.require()
)
@dispatch(
    Twilight([
        "action" @ UnionMatch("添加", "删除"),
        FullMatch("BOT管理"),
        WildcardMatch() @ "member_id"
        # 示例: 添加/删除 BOT管理 000
    ])
)
async def change_botAdmin(app: Ariadne, group: Group, action: RegexResult, member_id: RegexResult, source: Source):
    action = action.result.display
    targets = get_targets(member_id.result)
    admin_list = await Permission.get_BotAdminsList()
    error_targets = []
    for target in targets:
        if action == "添加":
            if target in admin_list:
                error_targets.append((target, f"{target}已经是BOT管理啦!"))
            else:
                await core.update_admins_permission([target])
        else:
            if target not in admin_list:
                error_targets.append((target, f"{target}还不是BOT管理哦!"))
            else:
                await orm.delete(
                    table=MemberPerm,
                    condition=[
                        MemberPerm.qq == target,
                    ]
                )
                await core.update_admins_permission()
    response_text = f"共解析{len(targets)}个目标\n其中{len(targets) - len(error_targets)}个执行成功,{len(error_targets)}个失败"
    if error_targets:
        response_text += "\n\n失败目标:"
        for i in error_targets:
            response_text += f"\n{i[0]}-{i[1]}"
    return await app.send_message(group, response_text, quote=source)


@listen(GroupMessage)
@decorate(
    Permission.user_require(Permission.GroupAdmin, if_noticed=True),
    Permission.group_require(channel.metadata.level, if_noticed=True),
    Function.require(channel.module),
    FrequencyLimitation.require(channel.module),
    Distribute.require()
)
@dispatch(Twilight([
    FullMatch("BOT管理列表"),
    # 示例: BOT管理列表
]))
async def get_botAdmins_list(app: Ariadne, group: Group, source: Source):
    perm_list_column = [ColumnTitle(title="BOT管理列表")]
    admin_list = await Permission.get_BotAdminsList()
    if len(admin_list) == 0:
        return await app.send_message(group, MessageChain("当前还没有BOT管理哦~"), quote=source)
    for member_id in admin_list:
        try:
            member_item = await app.get_member(group, member_id)
        except:
            member_item = None
        perm_list_column.append(
            ColumnUserInfo(
                name=f"{member_item.name}({member_id})" if member_item else member_id,
                avatar=await get_user_avatar_url(member_id)
            )
        )
    perm_list_column = [Column(elements=perm_list_column[i: i + 20]) for i in range(0, len(perm_list_column), 20)]
    return await app.send_message(group, MessageChain(
        Image(data_bytes=await OneMockUI.gen(
            GenForm(columns=perm_list_column, color_type="dark")
        ))
    ), quote=source)
