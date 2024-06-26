import os
import re

import discord
from discord import Option, OptionChoice
from discord.utils import basic_autocomplete
from dotenv import load_dotenv
from google.cloud import firestore

import bstage_crawler
import discord_bot
import twitter_crawler
import weverse_crawler
from discord_bot import (DOMAIN_WEVERSE, DOMAIN_TWITTER, DOMAIN_X,
                         DOMAIN_BSTAGE)
from firebase import Firebase
from sns_type import SnsType

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]
firebase = Firebase()
bot = discord.Bot()


async def sns_preview(ctx, url):
    # 取出 domain
    match = re.search(r'https://(www\.)?([^/]+)', url)
    if match:
        domain = match.group(2)
        if domain == DOMAIN_TWITTER or domain == DOMAIN_X:
            pattern = r'(https://' + re.escape(domain) + r'/[^?]+)'
            match = re.search(pattern, url)
            if match:
                tweet_url = match.group(1)
                if tweet_url:
                    print("提取的推文連結:", tweet_url)
                    await ctx.defer()
                    sns_info = twitter_crawler.fetch_data(tweet_url)
                    await discord_bot.send_message(ctx, sns_info)
                else:
                    print("未找到推文連結")
        elif domain == DOMAIN_WEVERSE:
            match = re.search(r'(https://weverse.io/[^?]+)', url)
            if match:
                weverse_url = match.group(0)
                if weverse_url:
                    print("提取的推文連結:", weverse_url)
                    await ctx.defer()
                    sns_info = weverse_crawler.fetch_data(weverse_url)
                    await discord_bot.send_message(ctx, sns_info)
                else:
                    print("未找到推文連結")
        elif domain in DOMAIN_BSTAGE:
            pattern = r'(https://' + re.escape(domain) + r'/(story/feed/[^?]+|contents/[^?]+))'
            match = re.search(pattern, url)
            if match:
                bstage_url = match.group(1)
                if bstage_url:
                    print("提取的推文連結:", bstage_url)
                    await ctx.defer()
                    sns_info = bstage_crawler.fetch_data(bstage_url)
                    await discord_bot.send_message(ctx, sns_info)
            else:
                print("未找到推文連結")
    else:
        print("無法提取域名")


async def read_message(message):
    # 排除機器人本身的訊息，避免無限循環
    # role_mentions.member.id
    if message.author == bot.user:
        return
    username = message.author.nick
    # 取出 domain
    match = re.search(r'https://(www\.)?([^/]+)', message.content)
    if match:
        domain = match.group(2)
        if domain == DOMAIN_TWITTER or domain == DOMAIN_X:
            pattern = r'(https://' + re.escape(domain) + r'/[^?]+)'
            match = re.search(pattern, message.content)
            if match:
                tweet_url = match.group(1)
                await message.delete()
                loading_message = await message.channel.send(content="處理中，請稍後...")
                if tweet_url:
                    print("提取的推文連結:", tweet_url)
                    sns_info = twitter_crawler.fetch_data(tweet_url)
                    await message.channel.send(content=tweet_url,
                                               embeds=discord_bot.generate_embeds(username, sns_info))
                    if len(sns_info.videos) > 0:
                        await message.channel.send(content="\n".join(sns_info.videos))
                    await loading_message.delete()
                else:
                    print("未找到推文連結")
                    await loading_message.delete()
        elif domain == DOMAIN_WEVERSE:
            match = re.search(r'(https://weverse.io/[^?]+)', message.content)
            if match:
                weverse_url = match.group(0)
                await message.delete()
                loading_message = await message.channel.send(content="處理中，請稍後...")
                if weverse_url:
                    print("提取的推文連結:", weverse_url)
                    try:
                        await message.channel.send(content=weverse_url,
                                                   embeds=discord_bot.generate_embeds(username,
                                                                                      weverse_crawler.fetch_data(
                                                                                          weverse_url)))
                        await loading_message.delete()
                    except:
                        await loading_message.delete()
                else:
                    print("未找到推文連結")
                    await loading_message.delete()
        elif domain in DOMAIN_BSTAGE:
            pattern = r'(https://' + re.escape(domain) + r'/(story/feed/[^?]+|contents/[^?]+))'
            match = re.search(pattern, message.content)
            if match:
                bstage_url = match.group(1)
                await message.delete()
                loading_message = await message.channel.send(content="處理中，請稍後...")
                if bstage_url:
                    print("提取的推文連結:", bstage_url)
                    try:
                        sns_info = bstage_crawler.fetch_data(bstage_url)
                        content_list = [bstage_url]
                        if sns_info.videos is not None:
                            content_list.extend(sns_info.videos)
                        await message.channel.send(content="\n".join(content_list),
                                                   embeds=discord_bot.generate_embeds(username, sns_info))
                        await loading_message.delete()
                    except:
                        await loading_message.delete()
                else:
                    print("未找到推文連結")
                    await loading_message.delete()
        else:
            print("無法提取域名")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Bot is ready to receive commands')


@bot.slash_command(description="輸入網址產生預覽訊息 (支援網站: X, Weverse, b.stage)")
async def preview(ctx, link: Option(str, "請輸入連結", required=True, default='')):
    await sns_preview(ctx, link)


@bot.slash_command(description="訂閱 b.stage 帳號通知")
async def subscribe_bstage(ctx, link: Option(str, "請輸入要訂閱帳號的任一則發文連結", required=True, default='')):
    await add_bstage_account_to_firestore(ctx, link)


@bot.listen('on_message')
async def on_message(message):
    await read_message(message)


async def get_subscribed_list_from_firestore(ctx: discord.AutocompleteContext):
    tuple_list = firebase.get_subscribed_list_from_discord_id(SnsType.BSTAGE, ctx.interaction.channel.id)
    return [OptionChoice(name=username, value=id) for (username, id) in tuple_list]


async def remove_bstage_account_from_firestore(ctx, id):
    await ctx.defer()
    firebase.delete_account(SnsType.BSTAGE, id)
    await ctx.followup.send("取消訂閱成功")


@bot.slash_command(description="取消訂閱 b.stage 帳號通知")
async def unsubscribe_bstage(ctx, value: discord.Option(str, "選擇要取消訂閱的帳號",
                                                        autocomplete=basic_autocomplete(
                                                            get_subscribed_list_from_firestore))):
    await remove_bstage_account_from_firestore(ctx, value)


async def add_bstage_account_to_firestore(ctx, link):
    await ctx.defer()
    match = re.search(r'https://(.*)\.bstage\.in.*', link)
    if match:
        username = match.group(1)
        if firebase.is_account_exists(SnsType.BSTAGE, username):
            await ctx.followup.send(f"{username} 已訂閱過")
        else:
            firebase.add_account(SnsType.BSTAGE, id=username, username=username, discord_channel_id=ctx.channel.id,
                                 updated_at=firestore.SERVER_TIMESTAMP)
            await ctx.followup.send(f"{username} 訂閱成功")


bot.run(BOT_TOKEN)
