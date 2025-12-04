import time
import json
from typing import Dict

import aiohttp
from substrateinterface import Keypair

from utils.logger import Logger


class SubsquareClient:
    def __init__(self, config):
        self.config = config
        self.logger = Logger()
        self._keypair = None
        self.chain_slug = config.NETWORK_NAME.lower()
        self.base_url = f"https://{self.chain_slug}-api.subsquare.io"

    def _get_keypair(self):
        if self._keypair is None:
            self._keypair = Keypair.create_from_mnemonic(
                self.config.MNEMONIC,
                ss58_format=self.config.SUBSQUARE_SS58_FORMAT
            )
        return self._keypair

    @staticmethod
    def _quote_summary(summary: str) -> str:
        lines = [line.strip() for line in summary.strip().splitlines() if line.strip()]
        if not lines:
            return "No member feedback was submitted."
        return "\n> ".join(lines)

    def _build_content(
        self,
        referendum_index: int,
        title: str,
        vote_result: str,
        vote_counts: Dict[str, int],
        origin: str,
        summary: str,
        thread_url: str,
    ) -> str:
        quoted = self._quote_summary(summary)
        return (
            f"**BPA Alumni DAO Vote Summary**\n\n"
            f"- **Referendum** #{referendum_index}: {title}\n"
            f"- **Internal outcome**: **{vote_result.upper()}**\n"
            f"- **Internal tally**: AYE {vote_counts.get('aye', 0)} · "
            f"NAY {vote_counts.get('nay', 0)} · REC {vote_counts.get('recuse', 0)}\n"
            f"- **Origin/Track**: {origin}\n\n"
            f"**Feedback Summary**\n> {quoted}\n\n"
            f"[Internal discussion thread]({thread_url})\n\n"
            "If you would like to contact the alumni to discuss your proposal please reach out on "
            "[Discord](https://discord.com/invite/MsqrdQpGzp)."
        )

    async def post_feedback_comment(
        self,
        referendum_index: int,
        block_height: int,
        title: str,
        vote_result: str,
        vote_counts: Dict[str, int],
        origin: str,
        summary: str,
        thread_url: str,
    ):
        keypair = self._get_keypair()
        content = self._build_content(
            referendum_index=referendum_index,
            title=title,
            vote_result=vote_result,
            vote_counts=vote_counts,
            origin=origin,
            summary=summary,
            thread_url=thread_url,
        )
        entity = {
            "action": "comment",
            "indexer": {
                "pallet": "referenda",
                "object": "referendumInfoFor",
                "proposed_height": block_height,
                "id": referendum_index,
            },
            "content": content,
            "content_format": "subsquare_md",
            "timestamp": int(time.time() * 1000),
        }
        entity_json = json.dumps(entity, separators=(",", ":"))
        signature = keypair.sign(entity_json.encode()).hex()
        payload = {
            "entity": entity,
            "address": keypair.ss58_address,
            "signature": f"0x{signature}",
            "signer_wallet": "polkadot-js",
        }
        url = f"{self.base_url}/sima/referenda/{referendum_index}/comments"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                text = await response.text()
                if response.status >= 400:
                    self.logger.error(
                        f"Failed to post Subsquare comment on #{referendum_index}: {text}"
                    )
                    response.raise_for_status()
                self.logger.info(
                    f"Posted Subsquare comment for referendum #{referendum_index}"
                )
                return text

