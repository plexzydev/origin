package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

/**
 * Implosión: Colapsa todos los bloques hacia el punto central,
 * similar a una explosión hacia adentro.
 */
public class ImplodeEnchant extends CustomEnchant {

    public ImplodeEnchant() {
        super("implode", "§5💫 Implosión", 4,
                55_000, 27_500, EnchantRarity.EPIC,
                "Colapsa los bloques hacia el centro en una implosión devastadora.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int radius = level * 2 + 2;
        List<Block> affected = new ArrayList<>();

        // Recolectar todos los bloques del radio
        List<Block> candidates = new ArrayList<>();
        for (int x = -radius; x <= radius; x++) {
            for (int y = -radius; y <= radius; y++) {
                for (int z = -radius; z <= radius; z++) {
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        candidates.add(b);
                    }
                }
            }
        }

        // Ordenar por distancia al centro (más lejanos primero → colapsan hacia el centro)
        Location center = block.getLocation().add(0.5, 0.5, 0.5);
        candidates.sort((a, b2) ->
                Double.compare(b2.getLocation().distanceSquared(center),
                               a.getLocation().distanceSquared(center)));

        for (Block b : candidates) {
            affected.add(b);
            breakBlock(player, b);

            // Partículas dirigidas al centro
            Location bLoc = b.getLocation().add(0.5, 0.5, 0.5);
            player.getWorld().spawnParticle(Particle.CRIT_MAGIC, bLoc, 3, 0, 0, 0, 0.1);
        }

        player.getWorld().spawnParticle(Particle.EXPLOSION_LARGE, center, 5);
        player.getWorld().playSound(center, Sound.ENTITY_GENERIC_EXPLODE, 0.8f, 2.0f);
        return affected;
    }
}
