# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------
"""
This module implements classes derived from Message for representing
connection requests, connection replies, disconnection requests, and
keep alives. It also defines handler methods to be called when these
message types arrive.
"""

import logging

from gossip import common, message, node

logger = logging.getLogger(__name__)


def send_connection_request(gossiper, peer):
    """Sends a connection request (syn message) to a candidate peer node.

    Args:
        gossiper (Node): The local node.
        peer (Node): The remote node.
    """
    logger.info("add node %s, %s, %s", peer, peer.Identifier[:8],
                peer.NetAddress)

    gossiper.add_node(peer)

    request = ConnectSynMessage()
    request.NetHost = gossiper.LocalNode.endpoint_host
    request.NetPort = gossiper.LocalNode.endpoint_port
    request.Name = gossiper.LocalNode.Name

    gossiper.send_message(request, peer.Identifier)


def register_message_handlers(gossiper):
    """Registers the connection-related message handlers for a node.

    Args:
        gossiper (Node): The node to register message handlers on.
    """
    gossiper.register_message_handler(ConnectSynMessage,
                                      connect_syn_handler)
    gossiper.register_message_handler(ConnectAckMessage,
                                      connect_ack_handler)
    gossiper.register_message_handler(ConnectSynAckMessage,
                                      connect_syn_ack_handler)
    gossiper.register_message_handler(DisconnectRequestMessage,
                                      disconnect_request_handler)
    gossiper.register_message_handler(KeepAliveMessage, keep_alive_handler)


class ConnectSynMessage(message.Message):
    """Connection syn messages are sent to a candidate peer node to initiate a
    gossip connection.

    Attributes:
        ConnectSynMessage.MessageType (str): The class name of the message.
        Reliable (bool): Whether or not the message requires reliable
            delivery.
        NetHost (str): Hostname or IP address identifying the node.
        NetPort (int): The remote port number to connect to.
        Name (str): The name of the connection.
        IsSystemMessage (bool): Whether or not this is a system message.
            System messages have special delivery priority rules.
        IsForward (bool): Whether the message should be automatically
            forwarded.
        IsReliable (bool): Whether reliable delivery is required.
    """
    MessageType = "/gossip.messages.ConnectMessage/ConnectSyn"

    def __init__(self, minfo=None):
        """Constructor for the ConnectSynMessage class.

        Args:
            minfo (dict): Dictionary of values for message fields.
        """
        if minfo is None:
            minfo = {}
        super(ConnectSynMessage, self).__init__(minfo)
        self.Reliable = False

        self.NetHost = minfo.get('Host', "127.0.0.1")
        self.NetPort = minfo.get('Port', 0)
        self.Name = minfo.get('Name')

        self.IsSystemMessage = True
        self.IsForward = False
        self.IsReliable = True

    @property
    def NetAddress(self):
        """Returns the host and port of the connection request message.

        Returns:
            ordered pair: (host, port).
        """
        return (self.NetHost, self.NetPort)

    def dump(self):
        """Dumps a dict containing object attributes.

        Returns:
            dict: A mapping of object attribute names to values.
        """
        result = super(ConnectSynMessage, self).dump()

        result['Host'] = self.NetHost
        result['Port'] = self.NetPort
        result['Name'] = self.Name

        return result


def connect_syn_handler(msg, gossiper):
    """Handles connection syn events.

    When a connection syn message arrives, the requesting node is added
    as a node and an ack message is sent.  We do not yet know whether the
    requester can hear us, so we'll not set the node to a peer just yet.

    Args:
        msg (message.Message): The received connection request message.
        gossiper (Node): The local node.
    """
    if msg.OriginatorID in gossiper.blacklist:
        logger.warning('msg originator %s blacklisted', msg.OriginatorID)
        return

    if msg.SenderID != msg.OriginatorID:
        logger.error('connection request must originate from peer; %s not %s',
                     msg.OriginatorID, msg.SenderID)
        return

    name = msg.Name
    if not name:
        name = msg.OriginatorID[:8]

    orignode = node.Node(address=msg.NetAddress,
                         identifier=msg.OriginatorID,
                         name=name)
    gossiper.add_node(orignode)

    reply = ConnectAckMessage()
    reply.InReplyTo = msg.Identifier
    gossiper.send_message(reply, msg.OriginatorID)


class ConnectAckMessage(message.Message):
    """Connection ack messages are sent to a candidate peer node in response to
    an incoming connection syn message.

    Attributes:
        ConnectAckMessage.MessageType (str): The class name of the message.
        InReplyTo (str): The node identifier of the originator of the
            connection request message.
        IsSystemMessage (bool): Whether or not this is a system message.
            System messages have special delivery priority rules.
        IsForward (bool): Whether the message should be automatically
            forwarded.
        IsReliable (bool): Whether reliable delivery is required.
    """
    MessageType = "/gossip.messages.ConnectMessage/ConnectAck"

    def __init__(self, minfo=None):
        """Constructor for the ConnectAckMessage class.

        Args:
            minfo (dict): Dictionary of values for message fields.
        """
        if minfo is None:
            minfo = {}
        super(ConnectAckMessage, self).__init__(minfo)
        self.InReplyTo = minfo.get('InReplyTo', common.NullIdentifier)

        self.IsSystemMessage = True
        self.IsForward = False
        self.IsReliable = True

    def dump(self):
        """Dumps a dict containing object attributes.

        Returns:
            dict: A mapping of object attribute names to values.
        """
        result = super(ConnectAckMessage, self).dump()
        return result


def connect_ack_handler(msg, gossiper):
    """Handles connection ack events.

    When a connection ack message arrives, the local node can reason that 2-way
    communication with the replying node is (or was momentarily) possible, so
    it promotes the replying node from node to peer, and sends its new peer a
    syn_ack message.

    Args:
        msg (message.Message): The received connection reply message.
        gossiper (Node): The local node.
    """
    if msg.OriginatorID in gossiper.blacklist:
        logger.warning('msg originator %s blacklisted', msg.OriginatorID)
        return

    logger.info('received connect confirmation from node %s',
                gossiper.NodeMap.get(msg.OriginatorID, msg.OriginatorID[:8]))

    # we have confirmation that this peer is currently up, so add it to our
    # list
    if msg.OriginatorID in gossiper.NodeMap:
        gossiper.NodeMap[msg.OriginatorID].is_peer = True

    # send syn_ack back to new peer to demonstrate 2-way communication line
    reply = ConnectSynAckMessage()
    reply.InReplyTo = msg.Identifier
    gossiper.send_message(reply, msg.OriginatorID)


class ConnectSynAckMessage(message.Message):
    """Connection syn_ack messages are sent to a peer node in response to
    an incoming connection ack message, in order to allow the remote node to
    verify 2-way communication with the local node.

    Attributes:
        ConnectAckMessage.MessageType (str): The class name of the message.
        InReplyTo (str): The node identifier of the originator of the
            connection request message.
        IsSystemMessage (bool): Whether or not this is a system message.
            System messages have special delivery priority rules.
        IsForward (bool): Whether the message should be automatically
            forwarded.
        IsReliable (bool): Whether reliable delivery is required.
    """
    MessageType = "/gossip.messages.ConnectMessage/ConnectSynAck"

    def __init__(self, minfo=None):
        if minfo is None:
            minfo = {}
        super(ConnectSynAckMessage, self).__init__(minfo)
        self.InReplyTo = minfo.get('InReplyTo', common.NullIdentifier)
        self.IsSystemMessage = True
        self.IsForward = False
        self.IsReliable = True

    def dump(self):
        result = super(ConnectSynAckMessage, self).dump()
        return result


def connect_syn_ack_handler(msg, gossiper):
    """Handles connection syn_ack events.

    When a connection syn_ack message arrives, the local node can reason that
    2-way communication with the replying node is (or was momentarily)
    possible, so it promotes the replying node from node to peer, completing
    the three way handshake connection protocol.

    Args:
        msg (message.Message): The received connection reply message.
        gossiper (Node): The local node.
    """
    if msg.OriginatorID in gossiper.blacklist:
        logger.warning('msg originator %s blacklisted', msg.OriginatorID)
        return

    if msg.SenderID != msg.OriginatorID:
        logger.error('connection request must originate from peer; %s not %s',
                     msg.OriginatorID, msg.SenderID)
        return
    logger.info('received connect syn_ack from node %s',
                gossiper.NodeMap.get(msg.OriginatorID, msg.OriginatorID[:8]))
    # add peer now that we know 2-directional communication is possible
    if msg.OriginatorID in gossiper.NodeMap:
        gossiper.NodeMap[msg.OriginatorID].is_peer = True


class DisconnectRequestMessage(message.Message):
    """Disconnection request messages represent a request from a node
    to disconnect from the gossip network.

    Attributes:
        DisconnectRequestMessage.MessageType (str): The class name of the
            message.
        Reliable (bool): Whether or not the message requires reliable
            delivery.
        IsSystemMessage (bool): Whether or not this is a system message.
            System messages have special delivery priority rules.
        IsForward (bool): Whether the message should be automatically
            forwarded.
        IsReliable (bool): Whether reliable delivery is required.
    """
    MessageType = "/ConnectMessage/DisconnectRequest"

    def __init__(self, minfo=None):
        """Constructor for the DisconnectRequestMessage class.

        Args:
            minfo (dict): Dictionary of values for message fields.
        """
        if minfo is None:
            minfo = {}
        super(DisconnectRequestMessage, self).__init__(minfo)
        self.Reliable = False

        self.IsSystemMessage = True
        self.IsForward = False
        self.IsReliable = False

    def dump(self):
        """Dumps a dict containing object attributes.

        Returns:
            dict: A mapping of object attribute names to values.
        """
        return super(DisconnectRequestMessage, self).dump()


def disconnect_request_handler(msg, gossiper):
    """Handles disconnection request events.

    When a disconnection request message arrives, the replying node is
    removed as a peer.

    Args:
        msg (message.Message): The received disconnection request message.
        gossiper (Node): The local node.
    """
    logger.warn('received disconnect message from node %s',
                gossiper.NodeMap.get(msg.OriginatorID, msg.OriginatorID[:8]))

    # if this node is one of our peers, then drop it
    if msg.OriginatorID in gossiper.NodeMap:
        logger.warn('mark peer node %s as disabled',
                    gossiper.NodeMap[msg.OriginatorID])
        gossiper.drop_node(msg.OriginatorID)


class KeepAliveMessage(message.Message):
    """Keep alive messages represent a request from a node to keep the
    connection alive.

    Attributes:
        KeepAliveMessage.MessageType (str): The class name of the message.
        Reliable (bool): Whether or not the message requires reliable
            delivery.
        IsSystemMessage (bool): Whether or not this is a system message.
            System messages have special delivery priority rules.
        IsForward (bool): Whether the message should be automatically
            forwarded.
        IsReliable (bool): Whether reliable delivery is required.
    """
    MessageType = "/gossip.messages.ConnectMessage/KeepAlive"

    def __init__(self, minfo=None):
        """Constructor for the KeepAliveMessage class.

        Args:
            minfo (dict): Dictionary of values for message fields.
        """
        if minfo is None:
            minfo = {}
        super(KeepAliveMessage, self).__init__(minfo)
        self.Reliable = False

        self.IsSystemMessage = True
        self.IsForward = False
        self.IsReliable = False

    def dump(self):
        """Dumps a dict containing object attributes.

        Returns:
            dict: A mapping of object attribute names to values.
        """
        return super(KeepAliveMessage, self).dump()


def keep_alive_handler(msg, gossiper):
    """Handles keep alive events.

    Args:
        msg (message.Message): The received disconnection request message.
        gossiper (Node): The local node.
    """
    pass
