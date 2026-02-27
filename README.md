# NULLCHAIN

Everyone has a blockchain pitch. I wanted to see how much code was left after
removing the pitch. About one module, as it turns out.

NULLCHAIN is a local proof-of-work ledger: transfers, balances, sender nonces
and a JSON snapshot. No token sale, no peers, no wallet signatures. Account
names are labels. If you came here looking for the next currency to shill,
you've already misunderstood the repository.

## A chain in six commands

Python 3.10+, no dependencies. Run from this directory:

```sh
python3 nullchain.py init ledger.json --difficulty 2
python3 nullchain.py mine ledger.json --miner 3m3r1x
python3 nullchain.py send ledger.json --sender 3m3r1x --to ghost --amount 7
python3 nullchain.py mine ledger.json --miner 3m3r1x
python3 nullchain.py balance ledger.json ghost
# 7
python3 nullchain.py verify ledger.json
# valid
```

`show ledger.json` dumps the snapshot. Each mined block pays 50 units.
Difficulty means leading hexadecimal zeroes, from 1 to 4; leave it at 2 unless
you particularly enjoy watching Python count.

Balances include confirmed transfers. Queued transfers reserve funds and
advance the sender's nonce. A later queued transfer can spend an earlier
queued receipt, but not the reward for the block being mined. Yes, the order
matters. Moving the reward to the front changes the rules.

For scripted runs:

```python
from nullchain import Blockchain

chain = Blockchain(difficulty=2)
chain.mine("3m3r1x", timestamp=1)
chain.add_transaction("3m3r1x", "ghost", 7)
chain.mine("3m3r1x", timestamp=2)
assert chain.balance("ghost") == 7
assert chain.validate()

chain.save("ledger.json")
assert Blockchain.load("ledger.json").balance("ghost") == 7
```

Genesis is fixed for each difficulty and block times must increase. Loading a
snapshot replays the chain and checks the pending pool too. Editing a balance
in JSON is not an optimization; balances are derived from transactions.

Saving replaces the file atomically, including pending transfers. There is no
writer lock: two processes editing one snapshot can lose each other's work.
Networking and consensus between machines aren't implemented. If you propose
adding either, bring actual rules for conflicting histories, not a diagram.
