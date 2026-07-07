package dev.plexzy.prisongens.enchants;

import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.List;

/**
 * Clase base para todos los encantamientos personalizados.
 * Cada encantamiento implementa su propio comportamiento en {@link #onMine}.
 */
public abstract class CustomEnchant {

    protected final String id;
    protected final String displayName;
    protected final int maxLevel;
    protected final double baseCost;
    protected final long baseTokenCost;
    protected final EnchantRarity rarity;
    protected final String description;

    protected CustomEnchant(String id, String displayName, int maxLevel,
                             double baseCost, long baseTokenCost,
                             EnchantRarity rarity, String description) {
        this.id            = id;
        this.displayName   = displayName;
        this.maxLevel      = maxLevel;
        this.baseCost      = baseCost;
        this.baseTokenCost = baseTokenCost;
        this.rarity        = rarity;
        this.description   = description;
    }

    /**
     * Lógica principal del encantamiento.
     * Llamado cuando el jugador rompe un bloque en la mina.
     *
     * @param player   Jugador que mina
     * @param block    Bloque roto
     * @param level    Nivel actual del encantamiento
     * @param pickaxe  Pico usado
     * @return lista de bloques adicionales afectados (para XP, drops, etc.)
     */
    public abstract List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe);

    /**
     * Indica si el encantamiento puede coexistir con otro.
     * Por defecto, todos son compatibles.
     */
    public boolean isCompatible(CustomEnchant other) { return true; }

    /**
     * Costo para comprar/subir de nivel este encantamiento.
     */
    public double getCost(int currentLevel) {
        return baseCost * Math.pow(2.0, currentLevel);
    }

    public long getTokenCost(int currentLevel) {
        return (long) (baseTokenCost * Math.pow(2.0, currentLevel));
    }

    public String getId()            { return id; }
    public String getDisplayName()   { return displayName; }
    public int getMaxLevel()         { return maxLevel; }
    public EnchantRarity getRarity() { return rarity; }
    public String getDescription()   { return description; }

    // ── Utilidades comunes ────────────────────────────────────────────────────

    /**
     * Rompe un bloque como si fuera el jugador (drop, XP, etc.)
     */
    protected void breakBlock(Player player, Block block) {
        if (block == null || block.getType().isAir()) return;
        block.breakNaturally(player.getInventory().getItemInMainHand());
    }

    /**
     * Rompe un bloque silenciosamente sin drop.
     */
    protected void breakBlockSilent(Block block) {
        if (block == null || block.getType().isAir()) return;
        block.setType(org.bukkit.Material.AIR);
    }
}
