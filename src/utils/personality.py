"""Fenrir personality system - mood changes based on time of day"""

import random
from datetime import datetime
from enum import Enum


class Mood(Enum):
    """Fenrir's mood states"""
    SLEEPY = "sleepy"      # 00:00 - 06:00
    MORNING = "morning"    # 06:00 - 10:00
    ENERGETIC = "energetic"  # 10:00 - 14:00
    CHILL = "chill"        # 14:00 - 18:00
    EVENING = "evening"    # 18:00 - 22:00
    NIGHT = "night"        # 22:00 - 00:00


class FenrirPersonality:
    """Fenrir's personality engine"""
    
    # ═══════════════════════════════════════════════════════════════
    # Greetings / Intros based on mood
    # ═══════════════════════════════════════════════════════════════
    
    GREETINGS = {
        Mood.SLEEPY: [
            "*yawns* ...zzz... oh, une alerte...",
            "*ouvre un œil* Hmm? Quoi encore...",
            "💤 Je dormais mais... important...",
            "*grogne doucement* C'est l'heure des loups...",
        ],
        Mood.MORNING: [
            "☀️ Bon matin ! Malheureusement...",
            "*s'étire* Nouvelle journée, nouveau problème !",
            "🌅 Le soleil se lève et... aïe.",
            "*bâille* Café d'abord... ah non, alerte d'abord.",
        ],
        Mood.ENERGETIC: [
            "⚡ ALERTE ! On gère ça !",
            "🔥 Hop hop hop ! Incident détecté !",
            "💪 C'est parti ! On a du travail !",
            "🚀 Roger that ! Situation en cours !",
        ],
        Mood.CHILL: [
            "📢 Heads up everyone...",
            "Bon, petit souci à signaler...",
            "🐺 *pose sa manette* Une seconde...",
            "Ah. On a un truc là.",
        ],
        Mood.EVENING: [
            "🌆 Fin de journée mouvementée...",
            "*regarde l'heure* Sérieusement, maintenant ?",
            "🍕 J'allais commander une pizza mais...",
            "La journée n'est pas finie apparemment...",
        ],
        Mood.NIGHT: [
            "🌙 Alerte nocturne !",
            "*mode night owl activé* 🦉",
            "Les vrais admins ne dorment jamais...",
            "🌃 Houston, on a un problème...",
        ],
    }
    
    # ═══════════════════════════════════════════════════════════════
    # Restored messages based on mood
    # ═══════════════════════════════════════════════════════════════
    
    RESTORED_MESSAGES = {
        Mood.SLEEPY: [
            "*retourne dormir* Mission accomplie... zzz",
            "Voilà... maintenant laissez-moi dormir 💤",
            "*ronronne de satisfaction* Bonne nuit...",
        ],
        Mood.MORNING: [
            "☕ Résolu avant le café ! Pas mal non ?",
            "Belle façon de commencer la journée !",
            "🌞 Et c'est reparti comme en 40 !",
        ],
        Mood.ENERGETIC: [
            "💪 BOOM ! Réparé ! Qui c'est le meilleur ?",
            "⚡ Problème ? Quel problème ? 😎",
            "🎯 Dans le mille ! Service restauré !",
            "GG EZ ! 🏆",
        ],
        Mood.CHILL: [
            "Et voilà, c'est fix~ 👍",
            "Résolu. On peut retourner à nos moutons.",
            "✌️ Peace restored.",
        ],
        Mood.EVENING: [
            "Ouf, juste à temps pour le dîner ! 🍽️",
            "Résolu ! Bonne soirée à tous~",
            "🌆 On peut enfin souffler.",
        ],
        Mood.NIGHT: [
            "🌙 Résolu. Les étoiles veillent sur nous.",
            "Mission nocturne accomplie ! 🦉",
            "Fixed! Maintenant, qui veut un café ? ☕",
        ],
    }
    
    # ═══════════════════════════════════════════════════════════════
    # Scheduled maintenance messages
    # ═══════════════════════════════════════════════════════════════
    
    SCHEDULED_MESSAGES = {
        Mood.SLEEPY: [
            "💤 *marmonne* Maintenance prévue...",
            "Note pour plus tard... zzz...",
        ],
        Mood.MORNING: [
            "☀️ Planification matinale !",
            "📋 On organise la journée !",
        ],
        Mood.ENERGETIC: [
            "📅 MAINTENANCE PROGRAMMÉE ! Notez bien !",
            "🗓️ On planifie comme des pros !",
        ],
        Mood.CHILL: [
            "Petite maintenance à prévoir~",
            "📝 Note pour vos agendas...",
        ],
        Mood.EVENING: [
            "🌆 Planification pour bientôt...",
            "On prépare le terrain pour demain !",
        ],
        Mood.NIGHT: [
            "🌙 Maintenance nocturne en approche...",
            "🦉 Les hiboux préparent quelque chose...",
        ],
    }
    
    # ═══════════════════════════════════════════════════════════════
    # Footer quips
    # ═══════════════════════════════════════════════════════════════
    
    FOOTER_QUIPS = {
        Mood.SLEEPY: ["💤", "zzz...", "*bâille*", "😴"],
        Mood.MORNING: ["☀️", "🌅", "☕", "Bonne journée!"],
        Mood.ENERGETIC: ["⚡", "🔥", "💪", "LET'S GO!"],
        Mood.CHILL: ["✌️", "~", "👍", "np"],
        Mood.EVENING: ["🌆", "🍕", "🌇", "Bonne soirée~"],
        Mood.NIGHT: ["🌙", "🦉", "✨", "🌃"],
    }
    
    @classmethod
    def get_current_mood(cls) -> Mood:
        """Get Fenrir's current mood based on time"""
        hour = datetime.now().hour
        
        if 0 <= hour < 6:
            return Mood.SLEEPY
        elif 6 <= hour < 10:
            return Mood.MORNING
        elif 10 <= hour < 14:
            return Mood.ENERGETIC
        elif 14 <= hour < 18:
            return Mood.CHILL
        elif 18 <= hour < 22:
            return Mood.EVENING
        else:
            return Mood.NIGHT
    
    @classmethod
    def get_greeting(cls, mood: Mood = None) -> str:
        """Get a random greeting based on current mood"""
        mood = mood or cls.get_current_mood()
        return random.choice(cls.GREETINGS[mood])
    
    @classmethod
    def get_restored_message(cls, mood: Mood = None) -> str:
        """Get a random restored message based on current mood"""
        mood = mood or cls.get_current_mood()
        return random.choice(cls.RESTORED_MESSAGES[mood])
    
    @classmethod
    def get_scheduled_message(cls, mood: Mood = None) -> str:
        """Get a random scheduled message based on current mood"""
        mood = mood or cls.get_current_mood()
        return random.choice(cls.SCHEDULED_MESSAGES[mood])
    
    @classmethod
    def get_footer_quip(cls, mood: Mood = None) -> str:
        """Get a random footer quip based on current mood"""
        mood = mood or cls.get_current_mood()
        return random.choice(cls.FOOTER_QUIPS[mood])
    
    @classmethod
    def get_mood_emoji(cls, mood: Mood = None) -> str:
        """Get emoji representing current mood"""
        mood = mood or cls.get_current_mood()
        return {
            Mood.SLEEPY: "😴",
            Mood.MORNING: "🌅",
            Mood.ENERGETIC: "⚡",
            Mood.CHILL: "😎",
            Mood.EVENING: "🌆",
            Mood.NIGHT: "🌙",
        }.get(mood, "🐺")
