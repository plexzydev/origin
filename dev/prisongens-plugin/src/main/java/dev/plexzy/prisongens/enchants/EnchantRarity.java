package dev.plexzy.prisongens.enchants;

import org.bukkit.ChatColor;

public enum EnchantRarity {
    COMMON(ChatColor.WHITE,      "Común",    1.0),
    UNCOMMON(ChatColor.GREEN,    "Inusual",  1.5),
    RARE(ChatColor.AQUA,         "Raro",     2.0),
    EPIC(ChatColor.DARK_PURPLE,  "Épico",    3.0),
    LEGENDARY(ChatColor.GOLD,    "Legendario", 5.0),
    MYTHIC(ChatColor.DARK_RED,   "Mítico",   8.0);

    private final ChatColor color;
    private final String displayName;
    private final double costMultiplier;

    EnchantRarity(ChatColor color, String displayName, double costMultiplier) {
        this.color           = color;
        this.displayName     = displayName;
        this.costMultiplier  = costMultiplier;
    }

    public ChatColor getColor()         { return color; }
    public String getDisplayName()      { return displayName; }
    public double getCostMultiplier()   { return costMultiplier; }

    public String getColored() { return color + displayName; }
}
