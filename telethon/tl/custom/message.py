from .. import types
from ...utils import get_input_peer, get_peer_id, get_inner_text
from .messagebutton import MessageButton
from .forward import Forward


class Message:
    """
    Custom class that encapsulates a message providing an abstraction to
    easily access some commonly needed features (such as the markdown text
    or the text for a given message entity).

    Attributes:

        original_message (:tl:`Message`):
            The original :tl:`Message` object.

        Any other attribute:
            Attributes not described here are the same as those available
            in the original :tl:`Message`.
    """
    def __init__(self, client, original, entities, input_chat):
        # Share the original dictionary. Modifications to this
        # object should also be reflected in the original one.
        # This way there's no need to worry about get/setattr.
        self.__dict__ = original.__dict__
        self.original_message = original
        self.stringify = self.original_message.stringify
        self.to_dict = self.original_message.to_dict
        self._client = client
        self._text = None
        self._reply_message = None
        self._buttons = None
        self._buttons_flat = None
        self._buttons_count = None

        self._sender = entities.get(self.original_message.from_id)
        if self._sender:
            self._input_sender = get_input_peer(self._sender)
            if not getattr(self._input_sender, 'access_hash', None):
                self._input_sender = None
        else:
            self._input_sender = None

        # Determine the right chat where the message
        # was sent, not *to which ID* it was sent.
        if not self.original_message.out \
                and isinstance(self.original_message.to_id, types.PeerUser):
            self._chat_peer = types.PeerUser(self.original_message.from_id)
        else:
            self._chat_peer = self.original_message.to_id

        self._chat = entities.get(self.chat_id)
        self._input_chat = input_chat
        if not self._input_chat and self._chat:
            self._input_chat = get_input_peer(self._chat)
            if not getattr(self._input_sender, 'access_hash', None):
                # Telegram may omit the hash in updates -> invalid peer
                self._input_chat = None

        if getattr(self.original_message, 'fwd_from', None):
            self._forward = Forward(
                self._client, self.original_message.fwd_from, entities)
        else:
            self._forward = None

    def __new__(cls, client, original, entities, input_chat):
        if isinstance(original, types.Message):
            return super().__new__(_CustomMessage)
        elif isinstance(original, types.MessageService):
            return super().__new__(_CustomMessageService)
        else:
            return cls

    def __str__(self):
        return str(self.original_message)

    def __repr__(self):
        return repr(self.original_message)

    def __bytes__(self):
        return bytes(self.original_message)

    @property
    def client(self):
        """
        Returns the `telethon.telegram_client.TelegramClient` instance that
        created this instance.
        """
        return self._client

    @property
    def text(self):
        """
        The message text, formatted using the client's default parse mode.
        Will be ``None`` for :tl:`MessageService`.
        """
        if self._text is None and 'message' in self.__dict__:
            if not self._client.parse_mode:
                return self.__dict__['message']
            self._text = self._client.parse_mode.unparse(
                self.__dict__['message'], self.__dict__.get('entities'))

        return self._text

    @text.setter
    def text(self, value):
        if self._client.parse_mode:
            msg, ent = self._client.parse_mode.parse(value)
        else:
            msg, ent = value, []
        self.__dict__['message'] = msg
        self.__dict__['entities'] = ent
        self._text = value

    @property
    def raw_text(self):
        """
        The raw message text, ignoring any formatting.
        Will be ``None`` for :tl:`MessageService`.
        """
        return self.__dict__.get('message')

    @raw_text.setter
    def raw_text(self, value):
        self.__dict__['message'] = value
        self.__dict__['entities'] = []
        self._text = None

    @property
    def message(self):
        """
        The raw message text, ignoring any formatting.
        Will be ``None`` for :tl:`MessageService`.
        """
        return self.raw_text

    @message.setter
    def message(self, value):
        self.raw_text = value

    @property
    def action(self):
        """
        The :tl:`MessageAction` for the :tl:`MessageService`.
        Will be ``None`` for :tl:`Message`.
        """
        if isinstance(self.original_message, types.MessageService):
            return self.original_message.action

    # TODO Make a property for via_bot and via_input_bot, as well as get_*
    def _reload_message(self):
        """
        Re-fetches this message to reload the sender and chat entities,
        along with their input versions.
        """
        try:
            chat = self.get_input_chat() if self.is_channel else None
            msg = self._client.get_messages(
                chat, ids=self.original_message.id)
        except ValueError:
            return  # We may not have the input chat/get message failed
        if not msg:
            return  # The message may be deleted and it will be None

        self._sender = msg._sender
        self._input_sender = msg._input_sender
        self._chat = msg._chat
        self._input_chat = msg._input_chat

    @property
    def sender(self):
        """
        Returns the :tl:`User` that sent this message. It may be ``None``
        if the message has no sender or if Telegram didn't send the sender
        inside message events.

        If you're using `telethon.events`, use `get_sender` instead.
        """
        return self._sender

    def get_sender(self):
        """
        Returns `sender`, but will make an API call to find the
        sender unless it's already cached.
        """
        if self._sender is None and self.get_input_sender():
            try:
                self._sender =\
                    self._client.get_entity(self._input_sender)
            except ValueError:
                self._reload_message()
        return self._sender

    @property
    def chat(self):
        """
        Returns the :tl:`User`, :tl:`Chat` or :tl:`Channel` where this message
        was sent. It may be ``None`` if Telegram didn't send the chat inside
        message events.

        If you're using `telethon.events`, use `get_chat` instead.
        """
        return self._chat

    def get_chat(self):
        """
        Returns `chat`, but will make an API call to find the
        chat unless it's already cached.
        """
        if self._chat is None and self.get_input_chat():
            try:
                self._chat =\
                    self._client.get_entity(self._input_chat)
            except ValueError:
                self._reload_message()
        return self._chat

    @property
    def input_sender(self):
        """
        This (:tl:`InputPeer`) is the input version of the user who
        sent the message. Similarly to `input_chat`, this doesn't have
        things like username or similar, but still useful in some cases.

        Note that this might not be available if the library can't
        find the input chat, or if the message a broadcast on a channel.
        """
        if self._input_sender is None:
            if self.is_channel and not self.is_group:
                return None
            try:
                self._input_sender = self._client.session\
                    .get_input_entity(self.original_message.from_id)
            except ValueError:
                pass
        return self._input_sender

    def get_input_sender(self):
        """
        Returns `input_sender`, but will make an API call to find the
        input sender unless it's already cached.
        """
        if self.input_sender is None\
                and not self.is_channel and not self.is_group:
            self._reload_message()
        return self._input_sender

    @property
    def input_chat(self):
        """
        This (:tl:`InputPeer`) is the input version of the chat where the
        message was sent. Similarly to `input_sender`, this doesn't have
        things like username or similar, but still useful in some cases.

        Note that this might not be available if the library doesn't know
        where the message came from.
        """
        if self._input_chat is None:
            try:
                self._input_chat =\
                    self._client.session.get_input_entity(self._chat_peer)
            except ValueError:
                pass

        return self._input_chat

    def get_input_chat(self):
        """
        Returns `input_chat`, but will make an API call to find the
        input chat unless it's already cached.
        """
        if self.input_chat is None:
            # There's a chance that the chat is a recent new dialog.
            # The input chat cannot rely on ._reload_message() because
            # said method may need the input chat.
            target = self.chat_id
            for d in self._client.iter_dialogs(100):
                if d.id == target:
                    self._chat = d.entity
                    self._input_chat = d.input_entity
                    break

        return self._input_chat

    @property
    def sender_id(self):
        """
        Returns the marked sender integer ID, if present.
        """
        return self.original_message.from_id

    @property
    def chat_id(self):
        """
        Returns the marked chat integer ID. Note that this value **will
        be different** from `to_id` for incoming private messages, since
        the chat *to* which the messages go is to your own person, but
        the *chat* itself is with the one who sent the message.

        TL;DR; this gets the ID that you expect.
        """
        return get_peer_id(self._chat_peer)

    @property
    def is_private(self):
        """True if the message was sent as a private message."""
        return isinstance(self.original_message.to_id, types.PeerUser)

    @property
    def is_group(self):
        """True if the message was sent on a group or megagroup."""
        return (
            isinstance(self.original_message.to_id, (types.PeerChat,
                                                     types.PeerChannel))
            and not self.original_message.post
        )

    @property
    def is_channel(self):
        """True if the message was sent on a megagroup or channel."""
        return isinstance(self.original_message.to_id, types.PeerChannel)

    @property
    def is_reply(self):
        """True if the message is a reply to some other or not."""
        return bool(self.original_message.reply_to_msg_id)

    @property
    def forward(self):
        """
        Returns `telethon.tl.custom.forward.Forward` if the message
        has been forwarded from somewhere else.
        """
        return self._forward

    def _set_buttons(self, chat, bot):
        """
        Helper methods to set the buttons given the input sender and chat.
        """
        if isinstance(self.original_message.reply_markup, (
                types.ReplyInlineMarkup, types.ReplyKeyboardMarkup)):
            self._buttons = [[
                MessageButton(self._client, button, chat, bot,
                              self.original_message.id)
                for button in row.buttons
            ] for row in self.original_message.reply_markup.rows]
            self._buttons_flat = [x for row in self._buttons for x in row]

    def _needed_markup_bot(self):
        """
        Returns the input peer of the bot that's needed for the reply markup.

        This is necessary for :tl:`KeyboardButtonSwitchInline` since we need
        to know what bot we want to start. Raises ``ValueError`` if the bot
        cannot be found but is needed. Returns ``None`` if it's not needed.
        """
        for row in self.original_message.reply_markup.rows:
            for button in row.buttons:
                if isinstance(button, types.KeyboardButtonSwitchInline):
                    if button.same_peer:
                        bot = self.input_sender
                        if not bot:
                            raise ValueError('No input sender')
                    else:
                        return self._client.session.get_input_entity(
                            self.original_message.via_bot_id)

    @property
    def buttons(self):
        """
        Returns a matrix (list of lists) containing all buttons of the message
        as `telethon.tl.custom.messagebutton.MessageButton` instances.
        """
        if not isinstance(self.original_message, types.Message):
            return  # MessageService and MessageEmpty have no markup

        if self._buttons is None and self.original_message.reply_markup:
            if not self.input_chat:
                return
            try:
                bot = self._needed_markup_bot()
            except ValueError:
                return
            else:
                self._set_buttons(self._input_chat, bot)

        return self._buttons

    def get_buttons(self):
        """
        Returns `buttons`, but will make an API call to find the
        input chat (needed for the buttons) unless it's already cached.
        """
        if not self.buttons and isinstance(
                self.original_message, types.Message):
            chat = self.get_input_chat()
            if not chat:
                return
            try:
                bot = self._needed_markup_bot()
            except ValueError:
                self._reload_message()
                bot = self._needed_markup_bot()  # TODO use via_input_bot

            self._set_buttons(chat, bot)

        return self._buttons

    @property
    def button_count(self):
        """
        Returns the total button count.
        """
        if not isinstance(self.original_message, types.Message):
            return 0

        if self._buttons_count is None and isinstance(
                self.original_message.reply_markup, (
                        types.ReplyInlineMarkup, types.ReplyKeyboardMarkup
                )):
            self._buttons_count = sum(
                1
                for row in self.original_message.reply_markup.rows
                for _ in row.buttons
            )

        return self._buttons_count or 0

    @property
    def media(self):
        """
        Returns the media of the message.
        """
        if isinstance(self.original_message, types.Message):
            return self.original_message.media
        elif isinstance(self.original_message, types.MessageService):
            action = self.original_message.action
            if isinstance(action, types.MessageActionChatEditPhoto):
                return types.MessageMediaPhoto(action.photo)

    @property
    def photo(self):
        """
        If the message media is a photo,
        this returns the :tl:`Photo` object.
        """
        if isinstance(self.media, types.MessageMediaPhoto):
            if isinstance(self.media.photo, types.Photo):
                return self.media.photo

    @property
    def document(self):
        """
        If the message media is a document,
        this returns the :tl:`Document` object.
        """
        if isinstance(self.media, types.MessageMediaDocument):
            if isinstance(self.media.document, types.Document):
                return self.media.document

    def _document_by_attribute(self, kind, condition=None):
        """
        Helper method to return the document only if it has an attribute
        that's an instance of the given kind, and passes the condition.
        """
        doc = self.document
        if doc:
            for attr in doc.attributes:
                if isinstance(attr, kind):
                    if not condition or condition(doc):
                        return doc

    @property
    def audio(self):
        """
        If the message media is a document with an Audio attribute,
        this returns the :tl:`Document` object.
        """
        return self._document_by_attribute(types.DocumentAttributeAudio,
                                           lambda attr: not attr.voice)

    @property
    def voice(self):
        """
        If the message media is a document with a Voice attribute,
        this returns the :tl:`Document` object.
        """
        return self._document_by_attribute(types.DocumentAttributeAudio,
                                           lambda attr: attr.voice)

    @property
    def video(self):
        """
        If the message media is a document with a Video attribute,
        this returns the :tl:`Document` object.
        """
        return self._document_by_attribute(types.DocumentAttributeVideo)

    @property
    def video_note(self):
        """
        If the message media is a document with a Video attribute,
        this returns the :tl:`Document` object.
        """
        return self._document_by_attribute(types.DocumentAttributeVideo,
                                           lambda attr: attr.round_message)

    @property
    def gif(self):
        """
        If the message media is a document with an Animated attribute,
        this returns the :tl:`Document` object.
        """
        return self._document_by_attribute(types.DocumentAttributeAnimated)

    @property
    def sticker(self):
        """
        If the message media is a document with a Sticker attribute,
        this returns the :tl:`Document` object.
        """
        return self._document_by_attribute(types.DocumentAttributeSticker)

    @property
    def out(self):
        """
        Whether the message is outgoing (i.e. you sent it from
        another session) or incoming (i.e. someone else sent it).

        Note that messages in your own chat are always incoming,
        but this property will be ``True`` if you send a message
        to your own chat. Messages you forward to your chat are
        *not* considered outgoing, just like official clients
        display them.
        """
        return self.original_message.out

    def get_reply_message(self):
        """
        The `telethon.tl.custom.message.Message` that this message is replying
        to, or ``None``.

        Note that this will make a network call to fetch the message and
        will later be cached.
        """
        if self._reply_message is None:
            if not self.original_message.reply_to_msg_id:
                return None
            self._reply_message = self._client.get_messages(
                self.get_input_chat() if self.is_channel else None,
                ids=self.original_message.reply_to_msg_id
            )

        return self._reply_message

    def respond(self, *args, **kwargs):
        """
        Responds to the message (not as a reply). Shorthand for
        `telethon.telegram_client.TelegramClient.send_message` with
        ``entity`` already set.
        """
        return self._client.send_message(
            self.get_input_chat(), *args, **kwargs)

    def reply(self, *args, **kwargs):
        """
        Replies to the message (as a reply). Shorthand for
        `telethon.telegram_client.TelegramClient.send_message` with
        both ``entity`` and ``reply_to`` already set.
        """
        kwargs['reply_to'] = self.original_message.id
        return self._client.send_message(
            self.get_input_chat(), *args, **kwargs)

    def forward_to(self, *args, **kwargs):
        """
        Forwards the message. Shorthand for
        `telethon.telegram_client.TelegramClient.forward_messages` with
        both ``messages`` and ``from_peer`` already set.

        If you need to forward more than one message at once, don't use
        this `forward_to` method. Use a
        `telethon.telegram_client.TelegramClient` instance directly.
        """
        kwargs['messages'] = self.original_message.id
        kwargs['from_peer'] = self.get_input_chat()
        return self._client.forward_messages(*args, **kwargs)

    def edit(self, *args, **kwargs):
        """
        Edits the message iff it's outgoing. Shorthand for
        `telethon.telegram_client.TelegramClient.edit_message` with
        both ``entity`` and ``message`` already set.

        Returns ``None`` if the message was incoming, or the edited
        :tl:`Message` otherwise.
        """
        if self.original_message.fwd_from:
            return None
        if not self.original_message.out:
            if not isinstance(self.original_message.to_id, types.PeerUser):
                return None
            me = self._client.get_me(input_peer=True)
            if self.original_message.to_id.user_id != me.user_id:
                return None

        return self._client.edit_message(
            self.get_input_chat(), self.original_message,
            *args, **kwargs
        )

    def delete(self, *args, **kwargs):
        """
        Deletes the message. You're responsible for checking whether you
        have the permission to do so, or to except the error otherwise.
        Shorthand for
        `telethon.telegram_client.TelegramClient.delete_messages` with
        ``entity`` and ``message_ids`` already set.

        If you need to delete more than one message at once, don't use
        this `delete` method. Use a
        `telethon.telegram_client.TelegramClient` instance directly.
        """
        return self._client.delete_messages(
            self.get_input_chat(), [self.original_message],
            *args, **kwargs
        )

    def download_media(self, *args, **kwargs):
        """
        Downloads the media contained in the message, if any.
        `telethon.telegram_client.TelegramClient.download_media` with
        the ``message`` already set.
        """
        return self._client.download_media(
            self.original_message, *args, **kwargs)

    def get_entities_text(self, cls=None):
        """
        Returns a list of tuples [(:tl:`MessageEntity`, `str`)], the string
        being the inner text of the message entity (like bold, italics, etc).

        Args:
            cls (`type`):
                Returns entities matching this type only. For example,
                the following will print the text for all ``code`` entities:

                >>> from telethon.tl.types import MessageEntityCode
                >>>
                >>> m = Message(...)
                >>> for _, inner_text in m.get_entities_text(MessageEntityCode):
                >>>     print(inner_text)
        """
        ent = self.__dict__.get('entities')
        if not ent:
            return []

        if cls:
            ent = [c for c in ent if isinstance(c, cls)]

        texts = get_inner_text(self.__dict__.get('message'), ent)
        return list(zip(ent, texts))

    def click(self, i=None, j=None, *, text=None, filter=None):
        """
        Calls `telethon.tl.custom.messagebutton.MessageButton.click`
        for the specified button.

        Does nothing if the message has no buttons.

        Args:
            i (`int`):
                Clicks the i'th button (starting from the index 0).
                Will ``raise IndexError`` if out of bounds. Example:

                >>> message = Message(...)
                >>> # Clicking the 3rd button
                >>> # [button1] [button2]
                >>> # [     button3     ]
                >>> # [button4] [button5]
                >>> message.click(2)  # index

            j (`int`):
                Clicks the button at position (i, j), these being the
                indices for the (row, column) respectively. Example:

                >>> # Clicking the 2nd button on the 1st row.
                >>> # [button1] [button2]
                >>> # [     button3     ]
                >>> # [button4] [button5]
                >>> message.click(0, 1)  # (row, column)

                This is equivalent to ``message.buttons[0][1].click()``.

            text (`str` | `callable`):
                Clicks the first button with the text "text". This may
                also be a callable, like a ``re.compile(...).match``,
                and the text will be passed to it.

            filter (`callable`):
                Clicks the first button for which the callable
                returns ``True``. The callable should accept a single
                `telethon.tl.custom.messagebutton.MessageButton` argument.
        """
        if sum(int(x is not None) for x in (i, text, filter)) >= 2:
            raise ValueError('You can only set either of i, text or filter')

        if not self.get_buttons():
            return  # Accessing the property sets self._buttons[_flat]

        if text is not None:
            if callable(text):
                for button in self._buttons_flat:
                    if text(button.text):
                        return button.click()
            else:
                for button in self._buttons_flat:
                    if button.text == text:
                        return button.click()
            return

        if filter is not None:
            for button in self._buttons_flat:
                if filter(button):
                    return button.click()
            return

        if i is None:
            i = 0
        if j is None:
            return self._buttons_flat[i].click()
        else:
            return self._buttons[i][j].click()


class _CustomMessage(Message, types.Message):
    pass


class _CustomMessageService(Message, types.MessageService):
    pass
