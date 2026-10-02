"""Replay escrowed NFT English auctions, anti-sniping extensions, pull refunds and royalty settlement."""

from .validation import integer, identifier, chronological


class AuctionHouse:
    def __init__(self, config):
        self.balances = {
            identifier(k): integer(v) for k, v in config["balances"].items()
        }
        self.nfts = dict(config["nfts"])
        self.auctions = {}
        self.refunds = {}
        self.platform = identifier(config["platform"])
        self.fee = integer(config.get("fee_bps", 250), maximum=10000)
        self.total = sum(self.balances.values())

    def apply(self, e):
        kind = e["type"]
        time = e["timestamp"]
        key = identifier(e["id"])
        if kind == "create":
            seller = identifier(e["seller"])
            token = identifier(e["token"])
            end = integer(e["end"])
            royalty = integer(e.get("royalty_bps", 0), maximum=10000)
            if (
                key in self.auctions
                or self.nfts.get(token) != seller
                or end <= time
                or royalty + self.fee > 10000
            ):
                raise ValueError("invalid auction")
            self.nfts[token] = "escrow:" + key
            self.auctions[key] = {
                "seller": seller,
                "token": token,
                "end": end,
                "reserve": integer(e["reserve"], minimum=1),
                "extension": integer(e.get("extension", 0)),
                "increment": integer(e.get("minimum_increment", 1), minimum=1),
                "royalty_bps": royalty,
                "creator": identifier(e.get("creator", seller)),
                "bid": 0,
                "bidder": None,
                "status": "active",
            }
        elif kind == "bid":
            auction = self.auctions[key]
            bidder = identifier(e["bidder"])
            amount = integer(e["amount"], minimum=1)
            if (
                auction["status"] != "active"
                or time >= auction["end"]
                or bidder == auction["seller"]
                or amount
                < max(auction["reserve"], auction["bid"] + auction["increment"])
                or self.balances.get(bidder, 0) < amount
            ):
                raise ValueError("invalid bid")
            self.balances[bidder] -= amount
            if auction["bidder"]:
                self.refunds[auction["bidder"]] = (
                    self.refunds.get(auction["bidder"], 0) + auction["bid"]
                )
            auction["bid"] = amount
            auction["bidder"] = bidder
            if auction["end"] - time < auction["extension"]:
                auction["end"] = time + auction["extension"]
        elif kind == "refund":
            owner = identifier(e["owner"])
            amount = self.refunds.pop(owner, 0)
            if not amount:
                raise ValueError("no refund")
            self.balances[owner] = self.balances.get(owner, 0) + amount
        elif kind == "settle":
            auction = self.auctions[key]
            if auction["status"] != "active" or time < auction["end"]:
                raise ValueError("auction not settleable")
            auction["status"] = "settled"
            if auction["bidder"]:
                fee = auction["bid"] * self.fee // 10000
                royalty = auction["bid"] * auction["royalty_bps"] // 10000
                for owner, amount in (
                    (self.platform, fee),
                    (auction["creator"], royalty),
                    (auction["seller"], auction["bid"] - fee - royalty),
                ):
                    self.balances[owner] = self.balances.get(owner, 0) + amount
                self.nfts[auction["token"]] = auction["bidder"]
            else:
                self.nfts[auction["token"]] = auction["seller"]
        else:
            raise ValueError("unknown auction event")
        escrow = sum(
            a["bid"] for a in self.auctions.values() if a["status"] == "active"
        )
        if (
            sum(self.balances.values()) + sum(self.refunds.values()) + escrow
            != self.total
        ):
            raise ValueError("auction conservation failure")
        return {"type": kind, "id": key}


def analyze(data):
    engine = AuctionHouse(data["config"])
    events = [engine.apply(e) for e in chronological(data["events"])]
    return {
        "balances": engine.balances,
        "nft_owners": engine.nfts,
        "auctions": engine.auctions,
        "pending_refunds": engine.refunds,
        "initial_total": engine.total,
        "events": events,
    }
