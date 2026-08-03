# services/renderers.py
import chainlit as cl
from typing import Optional
from services.table_parser import extract_first_table

class ChainlitStream:
    """Single in-flight message for assistant text, plus small cards for tool status."""
    def __init__(self):
        self.status_msg: Optional[cl.Message] = None
        self.text_msg: Optional[cl.Message] = None
        self._status_lines: list[str] = []

    async def start(self, title: str = "**Analyzing your query…**"):
        self.status_msg = cl.Message(content=f"**{title}**\n\n_Status:_ initializing...")
        await self.status_msg.send()

    async def on_tool_call(self, name: str, args: str):
        self._status_lines.append(f"🛠️ **{name or 'tool'}** started")
        await self._update_status()

    async def on_tool_output(self, name: str, out: str):
        self._status_lines.append(f"✅ **{name or 'tool'}** completed")
        await self._update_status()

    async def _update_status(self):
        if not self.status_msg:
            self.status_msg = cl.Message(content="")
            await self.status_msg.send()
        body = ["**Run status**:"]
        body.extend(f"- {line}" for line in self._status_lines)
        self.status_msg.content = "\n".join(body)
        await self.status_msg.update()

    async def on_text_delta(self, token: str):
        if self.text_msg is None:
            # Create AFTER status so this sits below it in the chat.
            self.text_msg = cl.Message(content="")
            await self.text_msg.send()
        await self.text_msg.stream_token(token or "")

    async def on_visualization(self, element):
        """Attach a viz element to the current text message (Beta, drop-first)."""
        if self.text_msg is None:
            self.text_msg = cl.Message(content=" ")
            await self.text_msg.send()
        self.text_msg.elements = [element]
        await self.text_msg.update()

    async def on_text_done(self, text: str):
        if self.text_msg is None:
            self.text_msg = cl.Message(content=text or "")
            await self.text_msg.send()
            return

        # Optional: upgrade a markdown pipe-table to a DataFrame element
        if text:
            try:
                df, remainder = extract_first_table(text)
            except Exception:
                df, remainder = None, text

            if df is not None:
                self.text_msg.content = (remainder or " ").strip()
                try:
                    self.text_msg.elements = [cl.Dataframe(data=df, name="Results")]
                except Exception:
                    self.text_msg.content = text  # fallback to raw text
            else:
                self.text_msg.content = text

        await self.text_msg.update()

    # async def on_text_delta(self, token: str):
    #     if self.msg is None:
    #         await self.start()
    #     await self.msg.stream_token(token or "")

    # async def on_text_done(self, text: str):
    #     if self.msg is None:
    #         await self.start()

    #     text = (text or "").strip()
    #     df, remainder = extract_first_table(text)

    #     if df is not None:
    #         # Show narrative text (if any) and attach the table as an element
    #         self.msg.content = remainder or " "
    #         try:
    #             self.msg.elements = [cl.Dataframe(df=df, name="Results")]
    #         except Exception:
    #             # fallback: leave as text if element not available
    #             self.msg.content = text
    #     else:
    #         self.msg.content = text or self.msg.content

    #     await self.msg.update()

    # async def on_tool_call(self, name: str, args: str):
    #     await cl.Message(
    #         content=f"🛠️ Handing off to **{name or 'tool'}**…\n\n```json\n{(args or '')[:600]}\n```"
    #     ).send()

    # async def on_tool_output(self, name: str, out: str):
    #     await cl.Message(
    #         content=f"✅ **{name or 'tool'}** completed.\n\n```\n{(out or '')[:1000]}\n```"
    #     ).send()
