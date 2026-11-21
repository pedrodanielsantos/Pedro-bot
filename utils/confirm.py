import logging
import os

import discord
from dotenv import load_dotenv

from config.constants import SUCCESS_COLOR

logger = logging.getLogger("confirm")

load_dotenv()
# Optional custom emojis for confirm prompt buttons, as <:name:id>. Unset
# leaves the buttons text only.
CONFIRM_EMOJI = os.getenv("CONFIRM_EMOJI") or None
CANCEL_EMOJI = os.getenv("CANCEL_EMOJI") or None


class ConfirmView(discord.ui.LayoutView):
    """Two-button prompt that resolves once, replacing the buttons with the outcome.

    Subclasses implement on_confirm and on_cancel. Clicks after resolving are
    acknowledged and ignored. Set message to the sent prompt so expiry can edit it.
    """

    def __init__(
        self, header: str, prompt: str, *, confirm_label: str, cancel_label: str,
        expired_outcome: str, timeout: float,
    ):
        super().__init__(timeout=timeout)
        self.header = header
        self.expired_outcome = expired_outcome
        self.resolved = False
        self.message: discord.WebhookMessage | None = None

        self.text_display = discord.ui.TextDisplay(f"{header}\n{prompt}")

        confirm = discord.ui.Button(label=confirm_label, emoji=CONFIRM_EMOJI, style=discord.ButtonStyle.success)
        confirm.callback = self._confirm_clicked
        cancel = discord.ui.Button(label=cancel_label, emoji=CANCEL_EMOJI, style=discord.ButtonStyle.danger)
        cancel.callback = self._cancel_clicked
        self.button_row = discord.ui.ActionRow(confirm, cancel)

        self.container = discord.ui.Container(self.text_display, self.button_row, accent_color=SUCCESS_COLOR)
        self.add_item(self.container)

    def resolve(self, outcome: str):
        self.resolved = True
        self.text_display.content = f"{self.header}\n{outcome}"
        self.container.remove_item(self.button_row)
        self.stop()

    async def _confirm_clicked(self, interaction: discord.Interaction):
        if self.resolved:
            await interaction.response.defer()
            return
        await self.on_confirm(interaction)

    async def _cancel_clicked(self, interaction: discord.Interaction):
        if self.resolved:
            await interaction.response.defer()
            return
        await self.on_cancel(interaction)

    async def on_confirm(self, interaction: discord.Interaction):
        raise NotImplementedError

    async def on_cancel(self, interaction: discord.Interaction):
        raise NotImplementedError

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolve(self.expired_outcome)
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                logger.warning(f"Could not mark the {type(self).__name__} prompt as expired: {e}")
