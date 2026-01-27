"""
Spell checking module for Luma Tools.

Provides spell-checked QTextEdit widget using PyEnchant.
Falls back gracefully if PyEnchant is not available.
"""

import re
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QColor,
    QTextCursor,
    QAction,  # Qt6: QAction moved from QtWidgets to QtGui
)
from PySide6.QtWidgets import QTextEdit, QMenu

logger = logging.getLogger(__name__)

# Try to import enchant, gracefully degrade if not available
try:
    import enchant
    from enchant.tokenize import get_tokenizer, EmailFilter, URLFilter
    ENCHANT_AVAILABLE = True
except ImportError:
    ENCHANT_AVAILABLE = False
    logger.info("PyEnchant not available - spell checking disabled")


class SpellCheckHighlighter(QSyntaxHighlighter):
    """
    QSyntaxHighlighter that underlines misspelled words.

    Uses PyEnchant to check spelling and applies a red wavy underline
    to misspelled words.
    """

    # Regex to find words (letters and apostrophes)
    WORD_REGEX = re.compile(r"\b[A-Za-z']+\b")

    def __init__(self, document, language="en_US"):
        super().__init__(document)

        self.spell_format = QTextCharFormat()
        self.spell_format.setUnderlineColor(QColor("#ff6b6b"))
        self.spell_format.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)

        self.dict = None
        self.tokenizer = None

        if ENCHANT_AVAILABLE:
            try:
                # Try requested language, fall back to en_US, then any available
                if enchant.dict_exists(language):
                    self.dict = enchant.Dict(language)
                elif enchant.dict_exists("en_US"):
                    self.dict = enchant.Dict("en_US")
                elif enchant.dict_exists("en"):
                    self.dict = enchant.Dict("en")
                else:
                    available = enchant.list_languages()
                    if available:
                        self.dict = enchant.Dict(available[0])
                        logger.info(f"Using {available[0]} dictionary for spell check")

                if self.dict:
                    # Get tokenizer with email and URL filters
                    try:
                        self.tokenizer = get_tokenizer(
                            self.dict.tag,
                            filters=[EmailFilter, URLFilter]
                        )
                    except Exception:
                        # Fall back to basic tokenizer
                        self.tokenizer = get_tokenizer()

            except Exception as e:
                logger.error(f"Error initializing spell checker: {e}")
                self.dict = None

    def highlightBlock(self, text):
        """Highlight misspelled words in the text block."""
        if not self.dict or not text:
            return

        if self.tokenizer:
            # Use enchant tokenizer (handles emails, URLs, etc.)
            try:
                for word, pos in self.tokenizer(text):
                    if not self._check_word(word):
                        self.setFormat(pos, len(word), self.spell_format)
            except Exception:
                # Fall back to regex if tokenizer fails
                self._highlight_with_regex(text)
        else:
            self._highlight_with_regex(text)

    def _highlight_with_regex(self, text):
        """Fallback highlighting using regex."""
        for match in self.WORD_REGEX.finditer(text):
            word = match.group()
            if not self._check_word(word):
                self.setFormat(match.start(), len(word), self.spell_format)

    def _check_word(self, word):
        """Check if a word is spelled correctly."""
        if not word or len(word) < 2:
            return True

        # Skip words that are all uppercase (likely acronyms)
        if word.isupper():
            return True

        # Skip words with numbers
        if any(c.isdigit() for c in word):
            return True

        try:
            return self.dict.check(word)
        except Exception:
            return True

    def get_suggestions(self, word, max_suggestions=10):
        """Get spelling suggestions for a word."""
        if not self.dict:
            return []
        try:
            return self.dict.suggest(word)[:max_suggestions]
        except Exception:
            return []

    def add_to_dictionary(self, word):
        """Add a word to the personal dictionary."""
        if self.dict:
            try:
                self.dict.add(word)
                self.rehighlight()
            except Exception as e:
                logger.error(f"Error adding word to dictionary: {e}")

    def ignore_word(self, word):
        """Ignore a word for this session."""
        if self.dict:
            try:
                self.dict.add_to_session(word)
                self.rehighlight()
            except Exception as e:
                logger.error(f"Error ignoring word: {e}")


class SpellCheckTextEdit(QTextEdit):
    """
    QTextEdit with integrated spell checking.

    Features:
    - Red wavy underline on misspelled words
    - Right-click context menu with spelling suggestions
    - Add to dictionary / Ignore options
    """

    def __init__(self, parent=None, language="en_US"):
        super().__init__(parent)

        self.highlighter = None
        if ENCHANT_AVAILABLE:
            self.highlighter = SpellCheckHighlighter(self.document(), language)

    def contextMenuEvent(self, event):
        """Custom context menu with spell check suggestions."""
        menu = self.createStandardContextMenu()

        if not self.highlighter or not self.highlighter.dict:
            menu.exec_(event.globalPos())
            return

        # Get cursor at click position
        cursor = self.cursorForPosition(event.pos())
        cursor.select(QTextCursor.WordUnderCursor)
        word = cursor.selectedText()

        if word and not self.highlighter._check_word(word):
            # Word is misspelled - add suggestions
            suggestions = self.highlighter.get_suggestions(word)

            if suggestions or word:
                menu.insertSeparator(menu.actions()[0])

                # Add "Add to Dictionary" option
                add_action = QAction(f"Add '{word}' to Dictionary", menu)
                add_action.triggered.connect(
                    lambda checked=False, w=word: self._add_to_dictionary(w)
                )
                menu.insertAction(menu.actions()[0], add_action)

                # Add "Ignore" option
                ignore_action = QAction(f"Ignore '{word}'", menu)
                ignore_action.triggered.connect(
                    lambda checked=False, w=word: self._ignore_word(w)
                )
                menu.insertAction(menu.actions()[0], ignore_action)

                menu.insertSeparator(menu.actions()[0])

                if suggestions:
                    # Add suggestions submenu
                    suggestions_menu = QMenu("Spelling Suggestions", menu)
                    for suggestion in suggestions:
                        action = QAction(suggestion, suggestions_menu)
                        action.triggered.connect(
                            lambda checked=False, s=suggestion, c=cursor: self._replace_word(c, s)
                        )
                        suggestions_menu.addAction(action)
                    menu.insertMenu(menu.actions()[0], suggestions_menu)
                else:
                    no_suggestions = QAction("No suggestions", menu)
                    no_suggestions.setEnabled(False)
                    menu.insertAction(menu.actions()[0], no_suggestions)

        menu.exec_(event.globalPos())

    def _replace_word(self, cursor, replacement):
        """Replace the word at cursor with replacement."""
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        cursor.insertText(replacement)
        cursor.endEditBlock()

    def _add_to_dictionary(self, word):
        """Add word to personal dictionary."""
        if self.highlighter:
            self.highlighter.add_to_dictionary(word)

    def _ignore_word(self, word):
        """Ignore word for this session."""
        if self.highlighter:
            self.highlighter.ignore_word(word)

    def setLanguage(self, language):
        """Change the spell check language."""
        if ENCHANT_AVAILABLE:
            self.highlighter = SpellCheckHighlighter(self.document(), language)


def is_spell_check_available():
    """Check if spell checking is available."""
    return ENCHANT_AVAILABLE
