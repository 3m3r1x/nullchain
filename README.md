# NULLCHAIN

A ledger without the pitch deck. Starting with blocks and transaction IDs;
people keep making this sound more mysterious than it is.

## Usage

```python
from nullchain import Blockchain

chain = Blockchain(difficulty=1)
print(chain.blocks[0].hash)
chain.mine("3m3r1x", timestamp=1)
chain.add_transaction("3m3r1x", "ghost", 7)
chain.mine("3m3r1x", timestamp=2)
```
