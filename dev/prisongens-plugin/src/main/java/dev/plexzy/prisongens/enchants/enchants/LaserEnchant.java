package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.util.Vector;

import java.util.ArrayList;
import java.util.List;

public class LaserEnchant extends CustomEnchant {

    public LaserEnchant() {
        super("laser", "§e⚡ Láser", 5,
                25_000, 12_500, EnchantRarity.EPIC,
                "Dispara un rayo láser que atraviesa bloques en línea recta.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int range = level * 3 + 5; // Nivel 1 → 8, Nivel 5 → 20
        List<Block> affected = new ArrayList<>();

        Vector direction = player.getLocation().getDirection().normalize();

        for (int i = 1; i <= range; i++) {
            Location point = block.getLocation().add(
                    direction.getX() * i,
                    direction.getY() * i,
                    direction.getZ() * i);
            Block b = point.getBlock();

            // Partículas del rayo
            player.getWorld().spawnParticle(Particle.REDSTONE, point,
                    3, 0, 0, 0, 0,
                    new Particle.DustOptions(Color.fromRGB(255, 50, 50), 1.5f));

            if (!b.getType().isAir() && b.getType() != Material.BEDROCK) {
                affected.add(b);
                breakBlock(player, b);
            }
        }

        player.getWorld().playSound(block.getLocation(),
                Sound.BLOCK_BEACON_ACTIVATE, 0.5f, 2.0f);

        return affected;
    }
}
