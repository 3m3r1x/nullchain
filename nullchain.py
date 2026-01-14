"""NULLCHAIN: a local proof-of-work ledger."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time


REWARD = 50
COINBASE = "$coinbase"
ZERO_HASH = "0" * 64
MAX_AMOUNT = (1 << 63) - 1


def _integer(value, name, minimum=0, maximum=MAX_AMOUNT):
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def _address(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise ValueError("invalid address")
    return value


def _fields(data, names):
    if type(data) is not dict or not set(names).issubset(data):
        raise ValueError("invalid record fields")


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


@dataclass(frozen=True)
class Transaction:
    sender: str
    recipient: str
    amount: int
    nonce: int

    def __post_init__(self):
        if self.sender != COINBASE:
            _address(self.sender)
        _address(self.recipient)
        _integer(self.amount, "amount", 1)
        _integer(self.nonce, "transaction nonce")

    def to_dict(self):
        return {"sender": self.sender, "recipient": self.recipient,
                "amount": self.amount, "nonce": self.nonce}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("sender", "recipient", "amount", "nonce"))
        return cls(**data)

    @property
    def id(self):
        return hashlib.sha256(canonical(self.to_dict())).hexdigest()


@dataclass(frozen=True)
class Block:
    index: int
    previous_hash: str
    timestamp: int
    difficulty: int
    nonce: int
    transactions: tuple

    def __post_init__(self):
        _integer(self.index, "block index")
        _integer(self.timestamp, "timestamp")
        _integer(self.difficulty, "difficulty", 1, 4)
        _integer(self.nonce, "proof nonce")
        if not isinstance(self.previous_hash, str) or re.fullmatch(r"[0-9a-f]{64}", self.previous_hash) is None:
            raise ValueError("invalid previous hash")
        if type(self.transactions) is not tuple or any(type(tx) is not Transaction for tx in self.transactions):
            raise ValueError("invalid transactions")

    def to_dict(self):
        return {"index": self.index, "previous_hash": self.previous_hash,
                "timestamp": self.timestamp, "difficulty": self.difficulty,
                "nonce": self.nonce,
                "transactions": [tx.to_dict() for tx in self.transactions]}

    @property
    def hash(self):
        return hashlib.sha256(canonical(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("index", "previous_hash", "timestamp", "difficulty",
                       "nonce", "transactions", "hash"))
        if type(data["transactions"]) is not list:
            raise ValueError("invalid transaction list")
        block = cls(data["index"], data["previous_hash"], data["timestamp"],
                    data["difficulty"], data["nonce"],
                    tuple(Transaction.from_dict(tx) for tx in data["transactions"]))
        if type(data["hash"]) is not str or data["hash"] != block.hash:
            raise ValueError("stored block hash does not match")
        return block


def _apply(tx, balances, nonces):
    if tx.sender == COINBASE:
        raise ValueError("coinbase is reserved for mining rewards")
    if tx.nonce != nonces.get(tx.sender, 0):
        raise ValueError("transaction nonce is out of order")
    if balances.get(tx.sender, 0) < tx.amount:
        raise ValueError("insufficient balance")
    balances[tx.sender] = balances.get(tx.sender, 0) - tx.amount
    balances[tx.recipient] = balances.get(tx.recipient, 0) + tx.amount
    nonces[tx.sender] = tx.nonce + 1


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


class Blockchain:
    def __init__(self, difficulty=2):
        self.difficulty = _integer(difficulty, "difficulty", 1, 4)
        self.blocks = [Block(0, ZERO_HASH, 0, self.difficulty, 0, ())]
        self.pending = []

    def _confirmed_state(self):
        _integer(self.difficulty, "difficulty", 1, 4)
        genesis = Block(0, ZERO_HASH, 0, self.difficulty, 0, ())
        if type(self.blocks) is not list or not self.blocks or self.blocks[0].index != 0:
            raise ValueError("invalid genesis block")
        balances, nonces = {}, {}
        for index, block in enumerate(self.blocks[1:], 1):
            if type(block) is not Block:
                raise ValueError("invalid block")
            previous = self.blocks[index - 1]
            if block.index != index or block.previous_hash != previous.hash:
                raise ValueError("broken block link")
            if block.timestamp <= previous.timestamp:
                raise ValueError("timestamps must increase")
            if not block.hash.startswith("0" * block.difficulty):
                raise ValueError("invalid proof of work")
        return balances, nonces

    def _pending_state(self):
        balances, nonces = self._confirmed_state()
        if type(self.pending) is not list or any(type(tx) is not Transaction for tx in self.pending):
            raise ValueError("invalid pending transactions")
        return balances, nonces

    def validate(self):
        self._pending_state()
        return True



    def mine(self, miner, timestamp=None):
        _address(miner)
        self._pending_state()
        previous = self.blocks[-1]
        if timestamp is None:
            timestamp = max(int(time.time()), previous.timestamp + 1)
        _integer(timestamp, "timestamp", previous.timestamp + 1)
        reward = Transaction(COINBASE, miner, REWARD, 0)
        transactions = (reward, *self.pending)
        nonce = 0
        while True:
            block = Block(len(self.blocks), previous.hash, timestamp,
                          self.difficulty, nonce, transactions)
            if block.hash.startswith("0" * self.difficulty):
                break
            nonce += 1
        self.blocks.append(block)
        self.pending.clear()
        return block
