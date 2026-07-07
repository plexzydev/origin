package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.*;

public class NukeEnchant extends CustomEnchant {

    public NukeEnchant() {
        super("nuke", "§4☢ Núcleo", 3,
                100_000, 50_000, EnchantRarity.LEGENDARY,
                "Lanza un ataque nuclear que destruye una zona enorme.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int radius = level * 5; // Nivel 1 → 5, Nivel 3 → 15
        List<Block> affected = new ArrayList<>();

        for (int x = -radius; x <= radius; x++) {
            for (int y = -3; y <= 3; y++) {
                for (int z = -radius; z <= radius; z++) {
                    double dist = Math.sqrt(x*x + z*z);
                    if (dist > radius) continue;
                    Block b = block.getRelative(x, y, z);
                    if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                        affected.add(b);
                        breakBlock(player, b);
                    }
                }
            }
        }

        Location loc = block.getLocation().add(0.5, 0.5, 0.5);
        player.getWorld().spawnParticle(Particle.EXPLOSION_HUGE, loc, 5, radius, 1, radius);
        player.getWorld().spawnParticle(Particle.SMOKE_LARGE,    loc, 50, radius, 1, radius);
        player.getWorld().playSound(loc, Sound.ENTITY_GENERIC_EXPLODE, 1f, 0.5f);
        player.getWorld().playSound(loc, Sound.ENTITY_LIGHTNING_BOLT_THUNDER, 1f, 0.7f);

        return affected;
    }
}
