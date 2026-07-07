package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

public class TornadoEnchant extends CustomEnchant {

    public TornadoEnchant() {
        super("tornado", "§3🌀 Tormenta", 5,
                35_000, 17_500, EnchantRarity.EPIC,
                "Crea un torbellino que destruye bloques en espiral.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int height = level + 2;
        int radius = level;
        List<Block> affected = new ArrayList<>();

        double angleStep = Math.PI / (radius * 4.0);

        for (int y = 0; y <= height; y++) {
            double angle = y * angleStep * 8;
            for (int r = 0; r <= radius; r++) {
                int dx = (int) Math.round(r * Math.cos(angle));
                int dz = (int) Math.round(r * Math.sin(angle));
                Block b = block.getRelative(dx, y, dz);

                if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                    affected.add(b);
                    breakBlock(player, b);
                }

                // Partícula espiral
                Location pLoc = b.getLocation().add(0.5, 0.5, 0.5);
                player.getWorld().spawnParticle(Particle.CLOUD, pLoc, 1, 0, 0, 0, 0);
            }
        }

        player.getWorld().playSound(block.getLocation(),
                Sound.ENTITY_LIGHTNING_BOLT_THUNDER, 0.4f, 1.8f);
        return affected;
    }
}
