import inspect

from . import _tl


# Which updates have the following fields?
_has_channel_id = []


# TODO EntityCache does the same. Reuse?
def _fill():
    for name in dir(_tl):
        update = getattr(_tl, name)
        if getattr(update, 'SUBCLASS_OF_ID', None) == 0x9f89304e:
            cid = update.CONSTRUCTOR_ID
            sig = inspect.signature(update.__init__)
            for param in sig.parameters.values():
                if param.name == 'channel_id' and param.annotation == int:
                    _has_channel_id.append(cid)

    if not _has_channel_id:
        raise RuntimeError('FIXME: Did the init signature or updates change?')


# We use a function to avoid cluttering the globals (with name/update/cid/doc)
_fill()


class StateCache:
    """
    In-memory update state cache, defaultdict-like behaviour.
    """
    def __init__(self, initial, loggers):
        # We only care about the pts and the date. By using a tuple which
        # is lightweight and immutable we can easily copy them around to
        # each update in case they need to fetch missing entities.
        self._logger = loggers[__name__]
        if initial:
            self._pts_date = initial.pts, initial.date
        else:
            self._pts_date = None, None

    def reset(self):
        self.__dict__.clear()
        self._pts_date = None, None

    # TODO Call this when receiving responses too...?
    def update(
            self,
            update,
            *,
            channel_id=None,
            has_pts=frozenset(x.CONSTRUCTOR_ID for x in (
                _tl.UpdateNewMessage,
                _tl.UpdateDeleteMessages,
                _tl.UpdateReadHistoryInbox,
                _tl.UpdateReadHistoryOutbox,
                _tl.UpdateWebPage,
                _tl.UpdateReadMessagesContents,
                _tl.UpdateEditMessage,
                _tl.updates.State,
                _tl.updates.DifferenceTooLong,
                _tl.UpdateShortMessage,
                _tl.UpdateShortChatMessage,
                _tl.UpdateShortSentMessage
            )),
            has_date=frozenset(x.CONSTRUCTOR_ID for x in (
                _tl.UpdateUserPhoto,
                _tl.UpdateEncryption,
                _tl.UpdateEncryptedMessagesRead,
                _tl.UpdateChatParticipantAdd,
                _tl.updates.DifferenceEmpty,
                _tl.UpdateShortMessage,
                _tl.UpdateShortChatMessage,
                _tl.UpdateShort,
                _tl.UpdatesCombined,
                _tl.Updates,
                _tl.UpdateShortSentMessage,
            )),
            has_channel_pts=frozenset(x.CONSTRUCTOR_ID for x in (
                _tl.UpdateChannelTooLong,
                _tl.UpdateNewChannelMessage,
                _tl.UpdateDeleteChannelMessages,
                _tl.UpdateEditChannelMessage,
                _tl.UpdateChannelWebPage,
                _tl.updates.ChannelDifferenceEmpty,
                _tl.updates.ChannelDifferenceTooLong,
                _tl.updates.ChannelDifference
            )),
            check_only=False
    ):
        """
        Update the state with the given update.
        """
        cid = update.CONSTRUCTOR_ID
        if check_only:
            return cid in has_pts or cid in has_date or cid in has_channel_pts

        if cid in has_pts:
            if cid in has_date:
                self._pts_date = update.pts, update.date
            else:
                self._pts_date = update.pts, self._pts_date[1]
        elif cid in has_date:
            self._pts_date = self._pts_date[0], update.date

        if cid in has_channel_pts:
            if channel_id is None:
                channel_id = self.get_channel_id(update)

            if channel_id is None:
                self._logger.info(
                    'Failed to retrieve channel_id from %s', update)
            else:
                self.__dict__[channel_id] = update.pts

    def get_channel_id(
            self,
            update,
            has_channel_id=frozenset(_has_channel_id),
            # Hardcoded because only some with message are for channels
            has_message=frozenset(x.CONSTRUCTOR_ID for x in (
                _tl.UpdateNewChannelMessage,
                _tl.UpdateEditChannelMessage
            ))
    ):
        """
        Gets the **unmarked** channel ID from this update, if it has any.

        Fails for ``*difference`` updates, where ``channel_id``
        is supposedly already known from the outside.
        """
        cid = update.CONSTRUCTOR_ID
        if cid in has_channel_id:
            return update.channel_id
        elif cid in has_message:
            if update.message.peer_id is None:
                # Telegram sometimes sends empty messages to give a newer pts:
                # UpdateNewChannelMessage(message=MessageEmpty(id), pts=pts, pts_count=1)
                # Not sure why, but it's safe to ignore them.
                self._logger.debug('Update has None peer_id %s', update)
            else:
                return update.message.peer_id.channel_id

        return None

    def __getitem__(self, item):
        """
        If `item` is `None`, returns the default ``(pts, date)``.

        If it's an **unmarked** channel ID, returns its ``pts``.

        If no information is known, ``pts`` will be `None`.
        """
        if item is None:
            return self._pts_date
        else:
            return self.__dict__.get(item)

    def __setitem__(self, where, value):
        if where is None:
            self._pts_date = value
        else:
            self.__dict__[where] = value