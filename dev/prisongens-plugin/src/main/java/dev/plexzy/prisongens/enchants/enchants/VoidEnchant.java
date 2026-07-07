package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

/**
 * Vacío: Destruye todos los bloques de una capa horizontal (Y fija).
 */
public class VoidEnchant extends CustomEnchant {

    public VoidEnchant() {
        super("void", "§0🕳 Vacío", 4,
                45_000, 22_500, EnchantRarity.EPIC,
                "Consume todos los bloques en una capa horizontal completa.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int radius = level * 3 + 3; // Nivel 1→6, Nivel 4→15
        List<Block> affected = new ArrayList<>();
        int y = block.getY();

        for (int x = -radius; x <= radius; x++) {
            for (int z = -radius; z <= radius; z++) {
                if (Math.sqrt(x*x + z*z) > radius) continue;
                Block b = block.getWorld().getBlockAt(
                        block.getX() + x, y, block.getZ() + z);
                if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                    affected.add(b);
                    breakBlock(player, b);

                    player.getWorld().spawnParticle(Particle.PORTAL,
                            b.getLocation().add(0.5, 0.5, 0.5), 2, 0, 0, 0, 0.3);
                }
            }
        }

        Location loc = block.getLocation().add(0.5, 0.5, 0.5);
        player.getWorld().spawnParticle(Particle.END_ROD, loc, 30, radius, 0, radius);
        player.getWorld().playSound(loc, Sound.ENTITY_ENDERMAN_TELEPORT, 0.6f, 0.7f);
        return affected;
    }
}
