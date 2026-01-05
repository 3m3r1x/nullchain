# NULLCHAIN

A ledger without the pitch deck. Starting with blocks and transaction IDs;
people keep making this sound more mysterious than it is.

## Usage

```python
from nullchain import Blockchain

chain = Blockchain(difficulty=1)
print(chain.blocks[0].hash)
```
