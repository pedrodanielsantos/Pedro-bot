from dataclasses import dataclass

import discord

# Discord's per-TextDisplay character limit.
TEXT_DISPLAY_LIMIT = 4000

# Select value for the entry that returns to page 0. Not a real label, so it
# can't collide with a target's own.
HOME_VALUE = "__home__"


@dataclass
class JumpTarget:
    """One entry in the jump select, pointing at the page a section starts on."""
    label: str
    page: int
    description: str | None = None


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text into pieces that fit Discord's per-TextDisplay character limit.

    Splits on line boundaries only, so a single line longer than the limit stays
    whole and is left to the caller.
    """
    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


class JumpSelect(discord.ui.Select):
    """Jumps straight to a section, with a home entry once off page 0."""

    def __init__(self, targets: list[JumpTarget], home_label: str, home_description: str | None, placeholder: str):
        self.targets = {target.label: target for target in targets}
        self.home_label = home_label
        self.home_description = home_description
        super().__init__(placeholder=placeholder, options=self._build_options(on_home=True))

    def _build_options(self, on_home: bool) -> list[discord.SelectOption]:
        options = []
        if not on_home:
            options.append(discord.SelectOption(label=self.home_label, description=self.home_description, value=HOME_VALUE))
        options += [
            discord.SelectOption(label=target.label, description=target.description, value=target.label)
            for target in self.targets.values()
        ]
        return options

    def refresh(self, on_home: bool):
        self.options = self._build_options(on_home)

    async def callback(self, interaction: discord.Interaction):
        view: PaginatorView = self.view
        value = self.values[0]
        page = 0 if value == HOME_VALUE else self.targets[value].page
        await view.go_to_page(interaction, page)


class PaginatorView(discord.ui.LayoutView):
    """Paged text in a single accent-colored container, with optional jump select.

    Pages are pre-rendered strings, each already within TEXT_DISPLAY_LIMIT.
    Page 0 is home: the jump select's home entry and every target page index are
    relative to it.
    """

    def __init__(
        self,
        pages: list[str],
        color,
        *,
        targets: list[JumpTarget] | None = None,
        home_label: str = "Home",
        home_description: str | None = None,
        placeholder: str = "Jump to a section...",
        timeout: float | None = 180,
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.message: discord.WebhookMessage | None = None

        self.text_display = discord.ui.TextDisplay(pages[0])

        # Everything lives in one Container so the select and buttons render
        # attached to the text, inside the same accent-colored box.
        self.container = discord.ui.Container(self.text_display, accent_color=color)

        self.jump_select = JumpSelect(targets, home_label, home_description, placeholder) if targets else None
        if self.jump_select:
            self.container.add_item(discord.ui.ActionRow(self.jump_select))

        # A lone page has nothing to navigate, so the row would only ever render
        # as five dead buttons.
        self.nav_row = None
        if len(pages) > 1:
            self.first_page = discord.ui.Button(label="<<", style=discord.ButtonStyle.secondary)
            self.first_page.callback = self._first_page
            self.prev_page = discord.ui.Button(label="<", style=discord.ButtonStyle.secondary)
            self.prev_page.callback = self._prev_page
            self.page_indicator = discord.ui.Button(style=discord.ButtonStyle.secondary, disabled=True)
            self.next_page = discord.ui.Button(label=">", style=discord.ButtonStyle.secondary)
            self.next_page.callback = self._next_page
            self.last_page = discord.ui.Button(label=">>", style=discord.ButtonStyle.secondary)
            self.last_page.callback = self._last_page
            self.nav_row = discord.ui.ActionRow(
                self.first_page, self.prev_page, self.page_indicator, self.next_page, self.last_page
            )
            self.container.add_item(self.nav_row)

        self.add_item(self.container)
        self.update_buttons()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass

    def update_buttons(self):
        if self.nav_row:
            self.first_page.disabled = (self.current_page == 0)
            self.prev_page.disabled = (self.current_page == 0)
            self.next_page.disabled = (self.current_page == len(self.pages) - 1)
            self.last_page.disabled = (self.current_page == len(self.pages) - 1)
            self.page_indicator.label = f"Page {self.current_page + 1}/{len(self.pages)}"
        if self.jump_select:
            self.jump_select.refresh(on_home=(self.current_page == 0))

    async def go_to_page(self, interaction: discord.Interaction, page: int):
        self.current_page = page
        self.text_display.content = self.pages[self.current_page]
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def _first_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, 0)

    async def _prev_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, max(0, self.current_page - 1))

    async def _next_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, min(len(self.pages) - 1, self.current_page + 1))

    async def _last_page(self, interaction: discord.Interaction):
        await self.go_to_page(interaction, len(self.pages) - 1)
