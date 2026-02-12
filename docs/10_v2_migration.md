# Telecraft V2 Migration

## Goal

Move from monolithic `MtprotoClient` usage to structured `Client` namespaces.

## Old vs New

- Old: `MtprotoClient.send_message(...)`
- New: `Client.messages.send(...)`

- Old: `MtprotoClient.send_file(...)`
- New: `Client.media.send_file(...)`

- Old: `MtprotoClient.add_user_to_group(...)`
- New: `Client.chats.members.add(...)`

- Old: `MtprotoClient.promote_admin(...)`
- New: `Client.admin.promote(...)`

- Old: `MtprotoClient.resolve_peer(...)`
- New: `Client.peers.resolve(...)`

- Old: `MtprotoClient.send_dice(...)`
- New: `Client.games.send(...)` / `Client.games.roll_dice(...)`

- Old: raw `messages.getSavedDialogs`
- New: `Client.saved.dialogs.list(...)`

- Old: raw `payments.getStarsStatus`
- New: `Client.stars.status(...)`

- Old: raw `payments.getStarGifts`
- New: `Client.gifts.catalog(...)`

- Old: raw `messages.getDialogs` / `messages.getDialogFilters`
- New: `Client.dialogs.list(...)` / `Client.dialogs.filters.list(...)`

- Old: raw sticker methods (`messages.getAllStickers`, `messages.searchStickers`)
- New: `Client.stickers.sets.all(...)` / `Client.stickers.search.stickers(...)`

- Old: raw topic/reaction methods
- New: `Client.topics.*` / `Client.reactions.*`

- Old: raw account privacy/notify methods
- New: `Client.privacy.*` / `Client.notifications.*`

- Old: raw business/chatlists/stories/channel-admin methods
- New: `Client.business.*`, `Client.chatlists.*`, `Client.stories.*`, `Client.channels.*`

- Old: raw search/drafts/report methods
- New: `Client.search.*`, `Client.drafts.*`, `Client.reports.*`

- Old: raw stats/recommendations methods
- New: `Client.stats.*`, `Client.discovery.*`

- Old: raw account sessions/themes/wallpapers methods
- New: `Client.account.*`

- Old: raw phone group-call methods
- New: `Client.calls.*`

- Old: raw takeout/webview/todo/translate methods
- New: `Client.takeout.*`, `Client.webapps.*`, `Client.todos.*`, `Client.translate.*`

## Example

```python
from telecraft.client import Client, ClientInit

client = Client(
    network="prod",
    session_path=".sessions/prod_dc4.session.json",
    init=ClientInit(api_id=12345, api_hash="..."),
)

await client.connect()
await client.messages.send("@username", "hi")
await client.media.send_file("@username", "pic.jpg")
await client.games.roll_dice("@username")
await client.saved.dialogs.list(limit=20)
await client.search.global_messages(q="invoice", limit=20)
await client.stars.status(peer="self")
await client.gifts.catalog()
await client.account.sessions.list()
await client.translate.text("hola", "en")
await client.close()
```

`GiftRef` public helper for gift operations:

```python
from telecraft.client import GiftRef

ref = GiftRef.user_msg(12345)
await client.gifts.saved.get([ref])
```

## Notes

- MTProto/Auth/Session internals are unchanged.
- For raw/low-level operations, use `telecraft.client.mtproto.MtprotoClient`.
