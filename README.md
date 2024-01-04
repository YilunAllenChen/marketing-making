# market-making bot

This repo is dedicated to the binance testnet coding challenge assignment for the Monoceros technical interview.

Example screenshot:
<img width="1027" alt="image" src="https://user-images.githubusercontent.com/32376517/208554988-a749b758-35eb-47ce-9857-72c45c9b96f8.png">


# High Level Design
The implementation focuses on extendability and configurability.

# Highlights

### Parameterized Strategy
Strategy is parameterized in a config file (in config.json), which can be easily altered by researchers / analysts without the need to reach into
source code. Also makes the deployment cycle much tighter, as changing the config file doesn't require a rebuild on the whole system.
One can even implement a periodic check in the strategy script on the content of the file to allow during-run-time adjustments.

### Extendable Architecture
The execution engine is designed such that extending its functionalities is made easier.

For example, the message handler part (in main.py) is very loosely entangled with the strategy logic (in portfolio.py), such that
in the future when we want to make the system distributed, or that we want to have multiple strategies
running together and we have need of a message queue, we can easily strip away the message handling and hook it up with a message
queue, and create another app that runs the strategy and consumes from that message queue.

### Local Copy + Eventual Consistency Model
For live position information, we initialize our portfolio by querying the RESTful API's, and then
start to listen to updates from websockets, updating local information as necessary. The information saved locally is designed to
be minimal such that it's guaranteed to be correct. This saves bandwidth and allows the strategy to react to events fast. To mitigate
the problem of inaccuracy, a periodic reset is also implemented such that in the unusual event that our updates are incorrect / stale,
we can still recover to a correct state.

This does expose us to considerable risk - if an erroneous state occurs and we just finished resetting, then until the next reset we
have incorrect information about where our positions are, and can make incorrect decisions. This problem can be minimized by tightening
up the reset cycle, but can't completely solve it. The ultimate way to solve it is to call the RESTful APIs to get deterministic state,
but that will be way too slow. Given the nature of this strategy, which requires us to constantly react to top-of-book changes, and also
given that our exposure to the market will be limited, I believe latency matters a lot more than accuracy. 

### Bulk Orders
All apis in this implementation are done in bulks, and only done if necessary. For example, if ask price changed, then all ask quotes, and
only all ask quotes, will be cancelled and resubmitted in one bulk. This minimizes back-and-forth traffic and is faster than doing them
one by one. One can further improve this by leveraging non-blocking calls (see potential improvements)

# Potential Improvements
### Async Optimizations
All of the calls in the program currently are blocking. This makes the execution incredibly suboptimal.
To improve this, we can create wrapper libraries that allow us to make non-blocking calls (for example, cancelling old orders and
creating new orders).

### Middlelayer Abstraction
We can create a unified set of APIs, IOW interface that all strategies can use to interact with different exchanges. This will make
onboarding new exchanges a lot easier.

### Distributed & Parallel Programming
Due to the existence of the infamous [GIL](https://realpython.com/python-gil/), python can never harness the power of true multi-threading.
This makes it hard to implement latency-sensitive complex strategies. Therefore, we should consider making the system distributed and consider
using faster languages to speed up parts of the business logic that don't require a lot of quant work.
