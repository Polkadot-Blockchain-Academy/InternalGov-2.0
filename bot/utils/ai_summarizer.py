import openai
from typing import List, Tuple, Dict
from utils.logger import Logger


class AISummarizer:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.logger = Logger()

    def summarize_comments(
        self,
        proposal_title: str,
        proposal_index: str,
        network_name: str,
        vote_result: str,
        vote_counts: Dict[str, int],
        origin: str,
        comments: List[Tuple],
        proposal_content: str = "",
    ) -> str:
        if not comments:
            return "No comments have been submitted for this proposal yet."

        prompt_sections = [
            "You are a chatbot specializing in Polkadot OpenGov, helping BPA Alumni DAO prepare vote summaries.",
            f"This job is for {network_name} referendum #{proposal_index} titled '{proposal_title}'.",
            f"The DAO voted {vote_result}. AYE: {vote_counts.get('aye', 0)}, NAY: {vote_counts.get('nay', 0)}, RECUSE: {vote_counts.get('recuse', 0)}. Origin: {origin}.",
            "Summarize the following feedback in a single past-tense paragraph (~100 words). Do not name voters.",
        ]

        if proposal_content:
            prompt_sections.append(f"Referendum context: {proposal_content[:400]}")

        for idx, (_, vote_type, comment, _) in enumerate(comments, 1):
            note = comment.strip() if comment and comment.strip() else "No comment."
            prompt_sections.append(f"Voter {idx} :: {vote_type.upper()} :: {note}")

        prompt = "\n\n".join(prompt_sections)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=220,
                temperature=0.9,
            )
            summary = response.choices[0].message.content.strip()
            self.logger.info(f"Generated summary for proposal #{proposal_index}")
            return summary
        except Exception as error:
            self.logger.error(f"Summary generation failed: {error}")
            return self._fallback_summary(vote_result, vote_counts, comments)

    def _fallback_summary(
        self,
        vote_result: str,
        vote_counts: Dict[str, int],
        comments: List[Tuple],
    ) -> str:
        core = f"BPA Alumni DAO voted {vote_result}. "
        core += f"Participation: {vote_counts.get('aye', 0)} aye, {vote_counts.get('nay', 0)} nay, {vote_counts.get('recuse', 0)} recuse. "

        highlights = [
            comment[:120].strip()
            for (_, _, comment, _) in comments
            if comment and comment.strip()
        ]
        if highlights:
            core += "Feedback touched on: " + "; ".join(highlights[:3])
            if len(highlights) > 3:
                core += f" (+{len(highlights) - 3} more comments)"
        else:
            core += "No written feedback was provided."

        return core
