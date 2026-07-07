package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

public class TsunamiEnchant extends CustomEnchant {

    public TsunamiEnchant() {
        super("tsunami", "§9🌊 Tsunami", 4,
                60_000, 30_000, EnchantRarity.EPIC,
                "Barre una fila entera de bloques de lado a lado.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int width  = level * 3;    // Anchura de la ola
        int depth  = level * 2 + 2; // Profundidad
        List<Block> affected = new ArrayList<>();

        for (int x = -width; x <= width; x++) {
            for (int z = 0; z <= depth; z++) {
                for (int y = -1; y <= 1; y++) {
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);
                    }
                    // Ola de partículas
                    player.getWorld().spawnParticle(Particle.WATER_SPLASH,
                            b.getLocation().add(0.5, 0.5, 0.5),
                            3, 0.2, 0.2, 0.2);
                }
            }
        }

        player.getWorld().playSound(block.getLocation(),
                Sound.ENTITY_GENERIC_SPLASH, 1f, 0.5f);
        return affected;
    }
}
