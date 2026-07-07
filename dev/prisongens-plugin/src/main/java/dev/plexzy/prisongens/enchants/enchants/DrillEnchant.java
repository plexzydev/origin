package dev.plexzy.prisongens.enchants.enchants;

import dev.plexzy.prisongens.enchants.CustomEnchant;
import dev.plexzy.prisongens.enchants.EnchantRarity;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.List;

public class DrillEnchant extends CustomEnchant {

    public DrillEnchant() {
        super("drill", "§b🔩 Taladro", 5,
                15_000, 7_500, EnchantRarity.RARE,
                "Perfora una línea de bloques hacia adelante.");
    }

    @Override
    public List<Block> onMine(Player player, Block block, int level, ItemStack pickaxe) {
        int depth = level * 2 + 2; // Nivel 1 → 4 bloques, Nivel 5 → 12 bloques
        List<Block> affected = new ArrayList<>();

        // Dirección a la que mira el jugador
        BlockFace face = getPlayerFace(player);
        Block current = block;

        for (int i = 0; i < depth; i++) {
            current = current.getRelative(face);
            if (!current.getType().isAir() && current.getType() != Material.BEDROCK) {
                affected.add(current);
                breakBlock(player, current);
            }
        }

        Location loc = block.getLocation().add(0.5, 0.5, 0.5);
        player.getWorld().spawnParticle(Particle.SMOKE_LARGE, loc, 15,
                face.getModX() * 0.5, face.getModY() * 0.5, face.getModZ() * 0.5);
        player.getWorld().playSound(loc, Sound.BLOCK_STONE_BREAK, 0.8f, 0.6f);

        return affected;
    }

    private BlockFace getPlayerFace(Player player) {
        float yaw = player.getLocation().getYaw();
        yaw = ((yaw % 360) + 360) % 360;
        if (yaw < 45 || yaw >= 315) return BlockFace.SOUTH;
        if (yaw < 135) return BlockFace.WEST;
        if (yaw < 225) return BlockFace.NORTH;
        return BlockFace.EAST;
    }
}
