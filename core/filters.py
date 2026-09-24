# -*- coding: utf-8 -*-
from pyrogram import filters

def self_cmd(commands: list):
    async def func(flt, client, message):
        if not message.text or not message.from_user or not message.from_user.is_self:
            return False
        
        text = message.text.strip()
        prefix = getattr(client, "custom_prefix", ".")
        prefix_enabled = getattr(client, "prefix_enabled", True)

        for cmd in flt.commands:
            if prefix_enabled and text.startswith(f"{prefix}{cmd}"):
                message.command_args = text[len(f"{prefix}{cmd}"):].strip()
                return True
            elif not prefix_enabled and text.startswith(cmd):
                message.command_args = text[len(cmd):].strip()
                return True
        return False
    return filters.create(func, commands=commands)
