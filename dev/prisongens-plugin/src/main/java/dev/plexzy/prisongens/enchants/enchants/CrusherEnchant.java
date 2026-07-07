package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

/**
 * Trituradora: Rompe una columna vertical completa hacia abajo.
 */
public class CrusherEnchant extends CustomEnchant {

    public CrusherEnchant() {
        super("crusher", "§8⚙ Trituradora", 5,
                18_000, 9_000, EnchantRarity.RARE,
                "Aplasta y rompe una columna vertical de bloques.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int depth  = level * 3 + 2; // Nivel 1→5, Nivel 5→17
        int width  = level > 2 ? 1 : 0;
        List<Block> affected = new ArrayList<>();

        for (int y = 0; y >= -depth; y--) {
            for (int x = -width; x <= width; x++) {
                for (int z = -width; z <= width; z++) {
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);

                        player.getWorld().spawnParticle(Particle.BLOCK_CRACK,
                                b.getLocation().add(0.5, 0.5, 0.5),
                                5, 0.3, 0.3, 0.3,
                                b.getBlockData());
                    }
                }
            }
        }

        player.getWorld().playSound(block.getLocation(),
                Sound.BLOCK_ANVIL_LAND, 0.5f, 1.4f);
        return affected;
    }
}
