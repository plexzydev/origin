package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

public class MegaExplosionEnchant extends CustomEnchant {

    public MegaExplosionEnchant() {
        super("mega_explosion", "§4💣 Mega Explosión", 5,
                50_000, 25_000, EnchantRarity.EPIC,
                "Rompe un área masiva de bloques en una sola explosión.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int radius = level + 2; // Nivel 1 → 3, Nivel 5 → 7
        List<Block> affected = new ArrayList<>();

        for (int x = -radius; x <= radius; x++) {
            for (int y = -radius; y <= radius; y++) {
                for (int z = -radius; z <= radius; z++) {
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);
                    }
                }
            }
        }

        Location loc = block.getLocation().add(0.5, 0.5, 0.5);
        player.getWorld().spawnParticle(Particle.EXPLOSION_HUGE, loc, 3);
        player.getWorld().spawnParticle(Particle.LAVA, loc, 30, 1, 1, 1);
        player.getWorld().playSound(loc, Sound.ENTITY_GENERIC_EXPLODE, 1f, 0.8f);
        player.getWorld().playSound(loc, Sound.ENTITY_LIGHTNING_BOLT_THUNDER, 0.5f, 1.2f);

        return affected;
    }
}
