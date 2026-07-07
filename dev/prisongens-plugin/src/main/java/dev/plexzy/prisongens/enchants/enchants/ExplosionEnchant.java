package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.Location;
import org.bukkit.Particle;
import org.bukkit.Sound;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

public class ExplosionEnchant extends CustomEnchant {

    public ExplosionEnchant() {
        super("explosion", "§c💥 Explosión", 5,
                10_000, 5_000, EnchantRarity.UNCOMMON,
                "Rompe bloques en un radio cuadrado.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int radius = level; // Nivel 1 → radio 1 (3x3), nivel 5 → radio 5 (11x11)
        List<Block> affected = new ArrayList<>();

        for (int x = -radius; x <= radius; x++) {
            for (int y = -1; y <= 1; y++) {
                for (int z = -radius; z <= radius; z++) {
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != org.bukkit.Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);
                    }
                }
            }
        }

        // Efectos
        Location loc = block.getLocation().add(0.5, 0.5, 0.5);
        player.getWorld().spawnParticle(Particle.EXPLOSION_LARGE, loc, 1);
        player.getWorld().playSound(loc, Sound.ENTITY_GENERIC_EXPLODE, 0.4f, 1.5f);

        return affected;
    }
}
