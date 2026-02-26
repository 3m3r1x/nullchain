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
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def _address(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise ValueError("invalid address")
    return value


def _fields(data, names):
    if type(data) is not dict or set(data) != set(names):
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
        if type(self.blocks) is not list or not self.blocks or self.blocks[0] != genesis:
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
            if block.difficulty != self.difficulty:
                raise ValueError("block difficulty does not match chain")
            if not block.hash.startswith("0" * self.difficulty):
                raise ValueError("invalid proof of work")
            if not block.transactions:
                raise ValueError("missing mining reward")
            reward = block.transactions[0]
            if reward.sender != COINBASE or reward.amount != REWARD or reward.nonce != 0:
                raise ValueError("invalid mining reward")
            for tx in block.transactions[1:]:
                _apply(tx, balances, nonces)
            balances[reward.recipient] = balances.get(reward.recipient, 0) + REWARD
        return balances, nonces

    def _pending_state(self):
        balances, nonces = self._confirmed_state()
        if type(self.pending) is not list or any(type(tx) is not Transaction for tx in self.pending):
            raise ValueError("invalid pending transactions")
        for tx in self.pending:
            _apply(tx, balances, nonces)
        return balances, nonces

    def validate(self):
        self._pending_state()
        return True

    def balance(self, address):
        _address(address)
        balances, _ = self._confirmed_state()
        return balances.get(address, 0)

    def add_transaction(self, sender, recipient, amount, nonce=None):
        _address(sender)
        _address(recipient)
        balances, nonces = self._pending_state()
        if nonce is None:
            nonce = nonces.get(sender, 0)
        tx = Transaction(sender, recipient, amount, nonce)
        _apply(tx, balances, nonces)
        self.pending.append(tx)
        return tx

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

    def to_dict(self):
        self.validate()
        return {"version": 1, "difficulty": self.difficulty,
                "blocks": [dict(block.to_dict(), hash=block.hash) for block in self.blocks],
                "pending": [tx.to_dict() for tx in self.pending]}

    @classmethod
    def from_dict(cls, data):
        _fields(data, ("version", "difficulty", "blocks", "pending"))
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported snapshot version")
        if type(data["blocks"]) is not list or type(data["pending"]) is not list:
            raise ValueError("invalid snapshot lists")
        chain = cls(data["difficulty"])
        chain.blocks = [Block.from_dict(block) for block in data["blocks"]]
        chain.pending = [Transaction.from_dict(tx) for tx in data["pending"]]
        chain.validate()
        return chain

    def save(self, path):
        path = Path(path)
        text = json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}.", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)
        return cls.from_dict(data)
