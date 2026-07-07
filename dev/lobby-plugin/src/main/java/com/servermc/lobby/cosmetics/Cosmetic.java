package com.servermc.lobby.cosmetics;

import org.bukkit.entity.Player;

/**
 * Base interface for all cosmetics.
 */
public interface Cosmetic {

    /**
     * Get the type of this cosmetic.
     */
    CosmeticType getType();

    /**
     * Called every tick to update the cosmetic effect.
     */
    void tick(Player player);

    /**
     * Called when the cosmetic is equipped/activated.
     */
    void equip(Player player);

    /**
     * Called when the cosmetic is unequipped/deactivated.
     */
    void unequip(Player player);
}
