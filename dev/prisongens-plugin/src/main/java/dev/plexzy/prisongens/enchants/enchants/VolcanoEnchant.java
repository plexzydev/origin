package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

public class VolcanoEnchant extends CustomEnchant {

    public VolcanoEnchant() {
        super("volcano", "§c🌋 Volcán", 3,
                80_000, 40_000, EnchantRarity.LEGENDARY,
                "Erupciona rompiendo bloques hacia arriba en forma de cono.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int maxHeight = level * 3;
        List<Block> affected = new ArrayList<>();

        for (int y = 0; y <= maxHeight; y++) {
            int r = maxHeight - y; // Radio decrece con la altura
            for (int x = -r; x <= r; x++) {
                for (int z = -r; z <= r; z++) {
                    if (Math.sqrt(x*x + z*z) > r) continue;
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);
                    }
                }
            }
            // Partículas de lava
            Location pLoc = block.getLocation().add(0, y, 0);
            player.getWorld().spawnParticle(Particle.LAVA, pLoc, 5 - y/2, r, 0, r);
        }

        player.getWorld().playSound(block.getLocation(),
                Sound.ENTITY_GENERIC_EXPLODE, 0.8f, 0.6f);
        return affected;
    }
}
