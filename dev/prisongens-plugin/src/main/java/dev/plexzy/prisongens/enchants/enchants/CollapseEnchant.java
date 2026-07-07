package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

/**
 * Colapso: Los bloques de arriba caen destruyendo los de abajo.
 * Destruye una columna entera hacia arriba.
 */
public class CollapseEnchant extends CustomEnchant {

    public CollapseEnchant() {
        super("collapse", "§6🏔 Colapso", 4,
                40_000, 20_000, EnchantRarity.EPIC,
                "Colapsa todas las capas superiores de la mina hacia abajo.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int height = level * 4 + 4; // Nivel 1→8, Nivel 4→20
        int radius = level + 1;
        List<Block> affected = new ArrayList<>();

        for (int y = 0; y <= height; y++) {
            for (int x = -radius; x <= radius; x++) {
                for (int z = -radius; z <= radius; z++) {
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);

                        player.getWorld().spawnParticle(Particle.FALLING_DUST,
                                b.getLocation().add(0.5, 0, 0.5),
                                3, 0.2, 0, 0.2,
                                b.getBlockData());
                    }
                }
            }
        }

        player.getWorld().playSound(block.getLocation(),
                Sound.BLOCK_GRAVEL_FALL, 1f, 0.6f);
        return affected;
    }
}
